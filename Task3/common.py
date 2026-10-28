from datetime import datetime, timezone

from fastapi import HTTPException, status


def validate_date_range(start: datetime, end: datetime) -> None:
    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must be earlier than end",
        )


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
