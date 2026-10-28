"""Task 4 - forecast next-hour PM2.5 using data fetched from the Task 3 API.

Pipeline: fetch recent hourly records from the API -> rebuild the Task 1 features
-> load the saved Task 1 model -> predict PM2.5 for the next hour.

Run from the repository root with the API running
(uvicorn api:app --app-dir Task3 --reload):

    python Task4/predict.py --source sql
    python Task4/predict.py --source mongo
    python Task4/predict.py --source sql --as-of 2014-06-15T12:00:00
    python Task4/predict.py --source csv          # offline test, no API needed

--as-of is the last observed hour. The forecast is for the hour after it. If that
next hour exists in the data, the script also prints the actual value and the error.
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

import joblib
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "Task1" / "results" / "beijing_pm25_model.joblib"
DEFAULT_CSV = ROOT / "Task1" / "results" / "beijing_records.csv"
DEFAULT_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# Same weather columns, in the same order, as the Task 1 notebook.
WEATHER = ["TEMP", "DEWP", "PRES", "Iws"]
# The longest feature needs 168 hours; the extra 24 cover the 3-hour forward fill.
HISTORY_HOURS = 192
ONE_HOUR = pd.Timedelta(hours=1)


class ForecastError(Exception):
    """A problem the user can fix (API down, too little data, bad file...)."""


# --------------------------------------------------------------------------- fetch
def _api_get(base_url: str, path: str, params: dict | None = None):
    url = f"{base_url.rstrip('/')}{path}"
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ForecastError(f"API request failed: {url} ({exc})") from exc
    return response.json()


def _tidy(frame: pd.DataFrame) -> pd.DataFrame:
    """Common cleanup: naive datetime index, numeric columns, sorted, no duplicates."""
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_localize(None)
    for column in ["pm2.5"] + WEATHER:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.drop_duplicates("timestamp").sort_values("timestamp")
    return frame.set_index("timestamp")[["pm2.5"] + WEATHER]


def _from_sql(rows: list[dict]) -> pd.DataFrame:
    """/sql/readings rows are flat: ts, pm25, dewp, temp, pres, cum_wind_speed, ..."""
    renamed = pd.DataFrame(rows).rename(columns={
        "ts": "timestamp", "pm25": "pm2.5", "dewp": "DEWP", "temp": "TEMP",
        "pres": "PRES", "cum_wind_speed": "Iws"})
    return _tidy(renamed)


def _from_mongo(docs: list[dict]) -> pd.DataFrame:
    """/mongo/readings documents are nested (air_quality, weather.wind, ...)."""
    flat = [{
        "timestamp": d["timestamp"],
        "pm2.5": d["air_quality"]["pm25"],
        "DEWP": d["weather"]["dewp"],
        "TEMP": d["weather"]["temp"],
        "PRES": d["weather"]["pres"],
        "Iws": d["weather"]["wind"]["cum_speed"],
    } for d in docs]
    return _tidy(pd.DataFrame(flat))


def _from_csv(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        raise ForecastError(f"CSV not found: {path}")
    raw = pd.read_csv(path, na_values=["NA"])
    raw["timestamp"] = pd.to_datetime(raw[["year", "month", "day", "hour"]])
    return _tidy(raw)


def latest_timestamp(source: str, base_url: str, csv_path: Path) -> pd.Timestamp:
    if source == "csv":
        return _from_csv(csv_path).index.max()
    record = _api_get(base_url, f"/{source}/readings/latest")
    value = record.get("timestamp") or record.get("ts")
    if value is None:
        raise ForecastError(f"Latest-record response has no timestamp: {record}")
    return pd.to_datetime(value, utc=True).tz_localize(None)


def fetch_range(source: str, base_url: str, start: pd.Timestamp, end: pd.Timestamp,
                csv_path: Path) -> pd.DataFrame:
    """Records with start <= timestamp < end (the API uses the same convention)."""
    if source == "csv":
        frame = _from_csv(csv_path)
        return frame.loc[(frame.index >= start) & (frame.index < end)]
    rows = _api_get(base_url, f"/{source}/readings",
                    {"start": start.isoformat(), "end": end.isoformat()})
    if not rows:
        raise ForecastError(f"The API returned no records between {start} and {end}")
    try:
        return _from_sql(rows) if source == "sql" else _from_mongo(rows)
    except KeyError as exc:
        raise ForecastError(f"Unexpected API response shape, missing field {exc}") from exc


# ------------------------------------------------------------------- preprocessing
def build_feature_row(history: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Rebuild the Task 1 features for the hour AFTER the last row of `history`.

    Mirrors the notebook exactly: PM2.5 forward-filled for at most 3 hours, lags 1/6/24,
    24h and 168h rolling means of the previous hours, weather from the previous hour,
    and calendar features of the hour being predicted.
    """
    target_time = history.index.max() + ONE_HOUR
    # Reindex to a complete hourly range so that shift() always means "N hours earlier".
    hourly = pd.date_range(history.index.min(), target_time, freq="h")
    df = history.reindex(hourly)

    df["pm_history"] = df["pm2.5"].ffill(limit=3)
    df["pm_lag_1"] = df["pm_history"].shift(1)
    df["pm_lag_6"] = df["pm_history"].shift(6)
    df["pm_lag_24"] = df["pm_history"].shift(24)
    df["pm_avg_24"] = df["pm_history"].shift(1).rolling(24, min_periods=24).mean()
    df["pm_avg_168"] = df["pm_history"].shift(1).rolling(168, min_periods=168).mean()
    for name in WEATHER:
        df[name + "_previous"] = df[name].shift(1)
    df["hour_of_day"] = df.index.hour
    df["month_of_year"] = df.index.month
    df["day_of_week"] = df.index.day_of_week

    missing_columns = [c for c in features if c not in df.columns]
    if missing_columns:
        raise ForecastError(f"The model expects features this script cannot build: {missing_columns}")
    row = df.loc[[target_time], features]
    empty = row.columns[row.isna().any()].tolist()
    if empty:
        raise ForecastError(
            "Not enough clean history to build these features: "
            f"{empty}. Fetched {len(history)} hourly rows; the 168-hour average needs "
            "168 consecutive hours with at most 3-hour PM2.5 gaps.")
    return row


# ------------------------------------------------------------------------- forecast
def forecast(args: argparse.Namespace) -> None:
    if not Path(args.model).exists():
        raise ForecastError(f"Model file not found: {args.model}")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bundle = joblib.load(args.model)
    if any(type(w.message).__name__ == "InconsistentVersionWarning" for w in caught):
        print("Note: the model was saved with a different scikit-learn version than the one "
              "installed. Ridge and StandardScaler are simple, so this is usually harmless.",
              file=sys.stderr)
    if not isinstance(bundle, dict) or "model" not in bundle or "features" not in bundle:
        raise ForecastError("Model file must be the Task 1 dict with 'model' and 'features'")
    model, features = bundle["model"], bundle["features"]

    as_of = pd.Timestamp(args.as_of) if args.as_of else latest_timestamp(
        args.source, args.base_url, args.csv)
    start = as_of - (HISTORY_HOURS - 1) * ONE_HOUR
    fetched = fetch_range(args.source, args.base_url, start, as_of + 2 * ONE_HOUR, args.csv)

    history = fetched.loc[:as_of]
    if history.empty or history.index.max() != as_of:
        raise ForecastError(f"No record found for {as_of}")

    row = build_feature_row(history, features)
    predicted = float(model.predict(row)[0])
    target_time = as_of + ONE_HOUR
    actual = fetched["pm2.5"].get(target_time)

    where = "CSV file" if args.source == "csv" else f"{args.source.upper()} API at {args.base_url}"
    print(f"Source:             {where} ({len(history)} hourly rows fetched)")
    print(f"Last observed hour: {as_of}")
    print(f"Forecast for:       {target_time}")
    print(f"Predicted PM2.5:    {predicted:.2f} ug/m3")
    if actual is not None and pd.notna(actual):
        print(f"Actual PM2.5:       {actual:.2f} ug/m3 (abs. error {abs(predicted - actual):.2f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast next-hour PM2.5 from the Task 3 API.")
    parser.add_argument("--source", choices=["sql", "mongo", "csv"], default="sql",
                        help="which API (or the local CSV for offline testing)")
    parser.add_argument("--base-url", default=DEFAULT_URL, help="API address (env API_BASE_URL)")
    parser.add_argument("--as-of", help="last observed hour, e.g. 2014-06-15T12:00:00 "
                                        "(default: the latest record)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="saved Task 1 model")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="CSV used with --source csv")
    args = parser.parse_args()
    try:
        forecast(args)
    except ForecastError as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()