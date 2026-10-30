import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# Database connection
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5433/beijing_air",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

router = APIRouter(prefix="/sql/air-quality", tags=["Air Quality"])


# Request model
class AirQualityReading(BaseModel):
    station_id: int
    ts: datetime
    pm25: Optional[int] = None


# Convert timezone-aware timestamps to UTC without timezone information.
def normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# Handle database errors
def handle_database_error(exc: SQLAlchemyError):
    if isinstance(exc, IntegrityError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Database constraint violation. Check that the station exists "
                "and that the reading does not duplicate an existing record."
            ),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Could not complete the database operation. "
            "Check that PostgreSQL is running and DATABASE_URL is correct."
        ),
    ) from exc


# =========================================================
# 1. CREATE - Insert a new air-quality reading
# POST /sql/air-quality
# =========================================================
@router.post("", status_code=status.HTTP_201_CREATED)
def create_reading(reading: AirQualityReading):
    values = reading.model_dump()
    values["ts"] = normalize_timestamp(reading.ts)

    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO air_quality_readings
                        (station_id, ts, pm25)
                    VALUES
                        (:station_id, :ts, :pm25)
                    RETURNING reading_id, station_id, ts, pm25
                    """
                ),
                values,
            )

            row = result.mappings().one()

        return dict(row)

    except SQLAlchemyError as exc:
        handle_database_error(exc)


# =========================================================
# 2. READ - Retrieve all air-quality readings
# GET /sql/air-quality
# =========================================================
@router.get("")
def get_all_readings():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                    SELECT reading_id, station_id, ts, pm25
                    FROM air_quality_readings
                    ORDER BY ts DESC
                    """
                )
            )

            rows = result.mappings().all()

        return [dict(row) for row in rows]

    except SQLAlchemyError as exc:
        handle_database_error(exc)


# =========================================================
# 3. READ - Retrieve the latest reading
# GET /sql/air-quality/latest
# =========================================================
@router.get("/latest")
def get_latest_reading():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                    SELECT reading_id, station_id, ts, pm25
                    FROM air_quality_readings
                    ORDER BY ts DESC
                    LIMIT 1
                    """
                )
            )

            row = result.mappings().first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No air-quality readings found.",
            )

        return dict(row)

    except HTTPException:
        raise

    except SQLAlchemyError as exc:
        handle_database_error(exc)


# =========================================================
# 4. UPDATE - Update an existing reading
# PUT /sql/air-quality/{reading_id}
# =========================================================
@router.put("/{reading_id}")
def update_reading(reading_id: int, reading: AirQualityReading):
    values = reading.model_dump()
    values["ts"] = normalize_timestamp(reading.ts)
    values["reading_id"] = reading_id

    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE air_quality_readings
                    SET station_id = :station_id,
                        ts = :ts,
                        pm25 = :pm25
                    WHERE reading_id = :reading_id
                    RETURNING reading_id, station_id, ts, pm25
                    """
                ),
                values,
            )

            row = result.mappings().first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reading with ID {reading_id} was not found.",
            )

        return dict(row)

    except HTTPException:
        raise

    except SQLAlchemyError as exc:
        handle_database_error(exc)


# =========================================================
# 5. DELETE - Delete an existing reading
# DELETE /sql/air-quality/{reading_id}
# =========================================================
@router.delete("/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reading(reading_id: int):
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    DELETE FROM air_quality_readings
                    WHERE reading_id = :reading_id
                    """
                ),
                {"reading_id": reading_id},
            )

            deleted = result.rowcount

        if deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reading with ID {reading_id} was not found.",
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise

    except SQLAlchemyError as exc:
        handle_database_error(exc)