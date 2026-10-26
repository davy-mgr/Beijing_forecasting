"""FastAPI application combining the SQL and MongoDB endpoint modules.

Run from the repository root with:
    uvicorn api:app --app-dir Task3 --reload
"""
from fastapi import FastAPI

from mongo_endpoints import ensure_timestamp_index, router as mongo_router
from sql_endpoints import router as sql_router

app = FastAPI(title="Beijing Air Quality API")
app.include_router(sql_router)
app.include_router(mongo_router)


@app.on_event("startup")
def create_mongo_indexes() -> None:
    ensure_timestamp_index()
