"""PostgreSQL CRUD and time-series endpoints."""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from common import utc_naive, validate_date_range

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/beijing_air",
)
engine = create_engine(DATABASE_URL)
router = APIRouter(prefix="/sql", tags=["SQL"])


class AirQualityReading(BaseModel):
    station_id: int
    ts: datetime
    pm25: Optional[int]


class WeatherReading(BaseModel):
    station_id: int
    ts: datetime
    dewp: Optional[float]
    temp: Optional[float]
    pres: Optional[float]
    wind_dir_id: Optional[int]
    cum_wind_speed: Optional[float]
    cum_snow_hours: Optional[int]
    cum_rain_hours: Optional[int]


def _sql_conflict(operation):
    try:
        return operation()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The reading conflicts with an existing record or database constraint",
        ) from exc


@router.get("/readings/latest")
def latest_sql_reading():
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM v_hourly_observations ORDER BY ts DESC LIMIT 1")
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No readings found")
    return dict(row)


@router.get("/readings")
def sql_readings_by_date_range(
    start: datetime = Query(..., description="Inclusive start timestamp"),
    end: datetime = Query(..., description="Exclusive end timestamp"),
):
    start = utc_naive(start)
    end = utc_naive(end)
    validate_date_range(start, end)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT * FROM v_hourly_observations "
                "WHERE ts >= :start AND ts < :end ORDER BY ts"
            ),
            {"start": start, "end": end},
        ).mappings().all()
    return [dict(row) for row in rows]


@router.post("/air-quality", status_code=status.HTTP_201_CREATED)
def create_air_quality_reading(reading: AirQualityReading):
    values = reading.dict()
    values["ts"] = utc_naive(reading.ts)

    def insert():
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "INSERT INTO air_quality_readings (station_id, ts, pm25) "
                    "VALUES (:station_id, :ts, :pm25) RETURNING reading_id"
                ),
                values,
            ).mappings().one()
        return {"reading_id": row["reading_id"], **values}

    return _sql_conflict(insert)


@router.get("/air-quality")
def list_air_quality_readings():
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT reading_id, station_id, ts, pm25 FROM air_quality_readings ORDER BY ts")
        ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/air-quality/{reading_id}")
def get_air_quality_reading(reading_id: int):
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT reading_id, station_id, ts, pm25 "
                "FROM air_quality_readings WHERE reading_id = :reading_id"
            ),
            {"reading_id": reading_id},
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
    return dict(row)


@router.put("/air-quality/{reading_id}")
def update_air_quality_reading(reading_id: int, reading: AirQualityReading):
    values = reading.dict()
    values["ts"] = utc_naive(reading.ts)

    def update():
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "UPDATE air_quality_readings SET station_id = :station_id, ts = :ts, "
                    "pm25 = :pm25 WHERE reading_id = :reading_id "
                    "RETURNING reading_id, station_id, ts, pm25"
                ),
                {"reading_id": reading_id, **values},
            ).mappings().first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
        return dict(row)

    return _sql_conflict(update)


@router.delete("/air-quality/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_air_quality_reading(reading_id: int):
    with engine.begin() as connection:
        result = connection.execute(
            text("DELETE FROM air_quality_readings WHERE reading_id = :reading_id"),
            {"reading_id": reading_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/weather", status_code=status.HTTP_201_CREATED)
def create_weather_reading(reading: WeatherReading):
    values = reading.dict()
    values["ts"] = utc_naive(reading.ts)

    def insert():
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "INSERT INTO weather_readings "
                    "(station_id, ts, dewp, temp, pres, wind_dir_id, cum_wind_speed, "
                    "cum_snow_hours, cum_rain_hours) "
                    "VALUES (:station_id, :ts, :dewp, :temp, :pres, :wind_dir_id, "
                    ":cum_wind_speed, :cum_snow_hours, :cum_rain_hours) "
                    "RETURNING reading_id"
                ),
                values,
            ).mappings().one()
        return {"reading_id": row["reading_id"], **values}

    return _sql_conflict(insert)


@router.get("/weather")
def list_weather_readings():
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT reading_id, station_id, ts, dewp, temp, pres, wind_dir_id, "
                "cum_wind_speed, cum_snow_hours, cum_rain_hours "
                "FROM weather_readings ORDER BY ts"
            )
        ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/weather/{reading_id}")
def get_weather_reading(reading_id: int):
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT reading_id, station_id, ts, dewp, temp, pres, wind_dir_id, "
                "cum_wind_speed, cum_snow_hours, cum_rain_hours "
                "FROM weather_readings WHERE reading_id = :reading_id"
            ),
            {"reading_id": reading_id},
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
    return dict(row)


@router.put("/weather/{reading_id}")
def update_weather_reading(reading_id: int, reading: WeatherReading):
    values = reading.dict()
    values["ts"] = utc_naive(reading.ts)

    def update():
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "UPDATE weather_readings SET station_id = :station_id, ts = :ts, "
                    "dewp = :dewp, temp = :temp, pres = :pres, wind_dir_id = :wind_dir_id, "
                    "cum_wind_speed = :cum_wind_speed, cum_snow_hours = :cum_snow_hours, "
                    "cum_rain_hours = :cum_rain_hours WHERE reading_id = :reading_id "
                    "RETURNING reading_id, station_id, ts, dewp, temp, pres, wind_dir_id, "
                    "cum_wind_speed, cum_snow_hours, cum_rain_hours"
                ),
                {"reading_id": reading_id, **values},
            ).mappings().first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
        return dict(row)

    return _sql_conflict(update)


@router.delete("/weather/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weather_reading(reading_id: int):
    with engine.begin() as connection:
        result = connection.execute(
            text("DELETE FROM weather_readings WHERE reading_id = :reading_id"),
            {"reading_id": reading_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
