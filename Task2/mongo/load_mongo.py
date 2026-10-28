import os
import sys

import pandas as pd
from pymongo import ASCENDING, MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "beijing_air"
COLLECTION = "readings"
BATCH = 5000

RENAME = {
    "pm2.5": "pm25", "DEWP": "dewp", "TEMP": "temp", "PRES": "pres",
    "cbwd": "wind_dir", "Iws": "cum_wind_speed", "Is": "snow_hours", "Ir": "rain_hours",
}


def clean(value, cast):
    """Return None for missing values and a plain Python type otherwise."""
    return None if pd.isna(value) else cast(value)


def to_document(r) -> dict:
    ts = r.ts.to_pydatetime()
    return {
        "timestamp": ts,
        "calendar": {
            "year": int(r.year), "month": int(r.month), "day": int(r.day),
            "hour": int(r.hour), "day_of_week": int(r.ts.dayofweek),  # Mon=0
        },
        "air_quality": {
            "station": "US Embassy Beijing",
            "pm25": clean(r.pm25, int),
        },
        "weather": {
            "station": "Beijing Capital International Airport",
            "dewp": clean(r.dewp, float),
            "temp": clean(r.temp, float),
            "pres": clean(r.pres, float),
            "wind": {
                "direction": clean(r.wind_dir, str),
                "cum_speed": clean(r.cum_wind_speed, float),
            },
            "snow_hours": clean(r.snow_hours, int),
            "rain_hours": clean(r.rain_hours, int),
        },
    }


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/PRSA_data_2010.1.1-2014.12.31.csv"
    df = pd.read_csv(path, na_values=["NA"]).rename(columns=RENAME)
    df["ts"] = pd.to_datetime(df[["year", "month", "day", "hour"]])
    df = df.sort_values("ts")

    col = MongoClient(MONGO_URI)[DB_NAME][COLLECTION]
    col.drop()

    batch, total = [], 0
    for row in df.itertuples(index=False):
        batch.append(to_document(row))
        if len(batch) == BATCH:
            col.insert_many(batch, ordered=False)
            total += len(batch)
            batch = []
    if batch:
        col.insert_many(batch, ordered=False)
        total += len(batch)

    col.create_index([("timestamp", ASCENDING)], unique=True)
    print(f"Inserted {total:,} documents into {DB_NAME}.{COLLECTION}")


if __name__ == "__main__":
    main()
