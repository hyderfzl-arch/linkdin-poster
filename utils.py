"""Small project-wide helpers."""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Return a timezone-aware UTC datetime, converting naive values."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
