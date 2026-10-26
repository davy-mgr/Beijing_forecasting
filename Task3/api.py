"""FastAPI application combining the SQL and MongoDB endpoint modules.

Run from the repository root with:
    uvicorn api:app --app-dir Task3 --reload
"""
import logging

from fastapi import FastAPI

from mongo_endpoints import ensure_timestamp_index, router as mongo_router
from sql_endpoints import router as sql_router

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Beijing Air Quality API")
app.include_router(sql_router)
app.include_router(mongo_router)


@app.get("/", tags=["Home"])
def root() -> dict[str, str]:
    """Return API entry points."""
    return {
        "message": "Beijing Air Quality API is running",
        "documentation": "/docs",
        "alternative_documentation": "/redoc",
        "health": "/health",
    }


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Report whether the API application is responding."""
    return {"status": "healthy", "service": "Beijing Air Quality API"}


@app.on_event("startup")
def create_mongo_indexes() -> None:
    ensure_timestamp_index()
    logger.info("Interactive API documentation: http://127.0.0.1:8000/docs")
