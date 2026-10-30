import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

from common import utc_naive, validate_date_range

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "beijing_air"
COLLECTION = "readings"

mongo_client = MongoClient(MONGO_URI)
mongo_collection = mongo_client[DB_NAME][COLLECTION]
router = APIRouter(prefix="/mongo", tags=["MongoDB"])


class WindReading(BaseModel):
    direction: Optional[str] = None
    cum_speed: Optional[float] = None


class AirQualityDocument(BaseModel):
    station: str = "US Embassy Beijing"
    pm25: Optional[int] = None


class WeatherDocument(BaseModel):
    station: str = "Beijing Capital International Airport"
    dewp: Optional[float] = None
    temp: Optional[float] = None
    pres: Optional[float] = None
    wind: WindReading = WindReading()
    snow_hours: Optional[int] = None
    rain_hours: Optional[int] = None


class CalendarDocument(BaseModel):
    year: int
    month: int
    day: int
    hour: int
    day_of_week: int


class MongoReading(BaseModel):
    timestamp: datetime
    calendar: Optional[CalendarDocument] = None
    air_quality: AirQualityDocument
    weather: WeatherDocument


def ensure_timestamp_index() -> None:
    mongo_collection.create_index([("timestamp", ASCENDING)], unique=True)


def _mongo_document(document: dict) -> dict:
    document.pop("_id", None)
    return document


@router.get("/readings/latest")
def latest_mongo_reading():
    document = mongo_collection.find_one({}, {"_id": False}, sort=[("timestamp", -1)])
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No readings found")
    return _mongo_document(document)


@router.get("/readings")
def mongo_readings(
    start: Optional[datetime] = Query(None, description="Inclusive start timestamp"),
    end: Optional[datetime] = Query(None, description="Exclusive end timestamp"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    """List readings, optionally filtering by an inclusive/exclusive date range."""
    query = {}
    if (start is None) != (end is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide both start and end timestamps, or neither.",
        )
    if start is not None and end is not None:
        start, end = utc_naive(start), utc_naive(end)
        validate_date_range(start, end)
        query["timestamp"] = {"$gte": start, "$lt": end}
    documents = mongo_collection.find(query, {"_id": False}).sort(
        "timestamp", ASCENDING
    ).skip(skip).limit(limit)
    return [_mongo_document(document) for document in documents]

@router.post("/readings", status_code=status.HTTP_201_CREATED)
def create_mongo_reading(reading: MongoReading):
    document = reading.model_dump() if hasattr(reading, "model_dump") else reading.dict()
    document["timestamp"] = utc_naive(reading.timestamp)
    if document.get("calendar") is None:
        ts = document["timestamp"]
        document["calendar"] = {"year": ts.year, "month": ts.month, "day": ts.day, "hour": ts.hour, "day_of_week": ts.weekday()}
    try:
        mongo_collection.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A reading already exists for this timestamp",
        ) from exc
    return _mongo_document(document)


@router.get("/readings/{timestamp}")
def get_mongo_reading(timestamp: datetime):
    timestamp = utc_naive(timestamp)
    document = mongo_collection.find_one({"timestamp": timestamp}, {"_id": False})
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
    return _mongo_document(document)


@router.put("/readings/{timestamp}")
def update_mongo_reading(timestamp: datetime, reading: MongoReading):
    timestamp = utc_naive(timestamp)
    if utc_naive(reading.timestamp) != timestamp:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The body timestamp must match the timestamp in the URL",
        )
    document = reading.model_dump() if hasattr(reading, "model_dump") else reading.dict()
    document["timestamp"] = timestamp
    result = mongo_collection.replace_one({"timestamp": timestamp}, document)
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
    return document


@router.delete("/readings/{timestamp}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mongo_reading(timestamp: datetime):
    timestamp = utc_naive(timestamp)
    result = mongo_collection.delete_one({"timestamp": timestamp})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
