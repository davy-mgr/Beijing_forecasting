"""MongoDB CRUD and time-series endpoints."""
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
    direction: Optional[str]
    cum_speed: Optional[float]


class AirQualityDocument(BaseModel):
    station: str
    pm25: Optional[int]


class WeatherDocument(BaseModel):
    station: str
    dewp: Optional[float]
    temp: Optional[float]
    pres: Optional[float]
    wind: WindReading
    snow_hours: Optional[int]
    rain_hours: Optional[int]


class CalendarDocument(BaseModel):
    year: int
    month: int
    day: int
    hour: int
    day_of_week: int


class MongoReading(BaseModel):
    timestamp: datetime
    calendar: CalendarDocument
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
def mongo_readings_by_date_range(
    start: datetime = Query(..., description="Inclusive start timestamp"),
    end: datetime = Query(..., description="Exclusive end timestamp"),
):
    start = utc_naive(start)
    end = utc_naive(end)
    validate_date_range(start, end)
    documents = mongo_collection.find(
        {"timestamp": {"$gte": start, "$lt": end}},
        {"_id": False},
    ).sort("timestamp", ASCENDING)
    return [_mongo_document(document) for document in documents]


@router.post("/readings", status_code=status.HTTP_201_CREATED)
def create_mongo_reading(reading: MongoReading):
    document = reading.dict()
    document["timestamp"] = utc_naive(reading.timestamp)
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
    document = reading.dict()
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
