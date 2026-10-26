"""Load the Beijing PM2.5 CSV into PostgreSQL.

Usage:
    python sql/load_sql.py data/PRSA_data_2010.1.1-2014.12.31.csv

Run sql/schema.sql first (it also resets the tables, so re-running is safe).
Raw values are loaded as-is: missing PM2.5 stays NULL.
"""
import os
import sys

import pandas as pd
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/beijing_air",
)
CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/PRSA_data_2010.1.1-2014.12.31.csv"
CHUNK = 2000


def read_raw(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, na_values=["NA"])
    df["ts"] = pd.to_datetime(df[["year", "month", "day", "hour"]])
    return df.sort_values("ts").reset_index(drop=True)


def main() -> None:
    df = read_raw(CSV_PATH)
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        stations = {r[0]: r[1] for r in conn.execute(text("SELECT name, station_id FROM stations"))}
        winds = {r[0]: r[1] for r in conn.execute(text("SELECT code, wind_dir_id FROM wind_directions"))}

        air = pd.DataFrame({
            "station_id": stations["US Embassy Beijing"],
            "ts": df["ts"],
            "pm25": df["pm2.5"].astype("Int64"),
        })
        weather = pd.DataFrame({
            "station_id": stations["Beijing Capital International Airport"],
            "ts": df["ts"],
            "dewp": df["DEWP"],
            "temp": df["TEMP"],
            "pres": df["PRES"],
            "wind_dir_id": df["cbwd"].map(winds).astype("Int64"),
            "cum_wind_speed": df["Iws"],
            "cum_snow_hours": df["Is"].astype("Int64"),
            "cum_rain_hours": df["Ir"].astype("Int64"),
        })

        air.to_sql("air_quality_readings", conn, if_exists="append",
                   index=False, method="multi", chunksize=CHUNK)
        weather.to_sql("weather_readings", conn, if_exists="append",
                       index=False, method="multi", chunksize=CHUNK)

    print(f"Loaded {len(df):,} rows into air_quality_readings and weather_readings")


if __name__ == "__main__":
    main()
