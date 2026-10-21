from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
UTC_TZ = timezone.utc


def get_utc_now() -> datetime:
    """Returns current datetime in UTC (timezone-aware)."""
    return datetime.now(UTC_TZ)


def get_tashkent_now() -> datetime:
    """Returns current datetime in Asia/Tashkent timezone."""
    return datetime.now(TASHKENT_TZ)


def to_tashkent(dt: Optional[datetime]) -> Optional[datetime]:
    """Converts a datetime to Asia/Tashkent timezone.
    If dt is naive, assumes UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(TASHKENT_TZ)


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Converts a datetime to UTC.
    If dt is naive, assumes Asia/Tashkent.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TASHKENT_TZ)
    return dt.astimezone(UTC_TZ)


def format_tashkent(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Formats datetime in Asia/Tashkent."""
    if dt is None:
        return "Noma'lum"
    t_dt = to_tashkent(dt)
    return t_dt.strftime(fmt)


def get_date_range_boundaries_utc(
    start_date: date, end_date: date
) -> tuple[datetime, datetime]:
    """Converts date range in Asia/Tashkent (both inclusive) to UTC datetime boundaries.
    Returns (start_utc_inclusive, end_utc_inclusive).
    """
    start_local = datetime.combine(start_date, time.min, tzinfo=TASHKENT_TZ)
    end_local = datetime.combine(end_date, time.max, tzinfo=TASHKENT_TZ)
    return start_local.astimezone(UTC_TZ), end_local.astimezone(UTC_TZ)
