from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from app.core.timezone import (
    to_tashkent,
    to_utc,
    format_tashkent,
    get_date_range_boundaries_utc,
    TASHKENT_TZ,
    UTC_TZ,
)


def test_timezone_conversion():
    # 2026-10-21 12:00 UTC -> 2026-10-21 17:00 Asia/Tashkent (UTC+5)
    utc_dt = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    tashkent_dt = to_tashkent(utc_dt)

    assert tashkent_dt.hour == 17
    assert tashkent_dt.day == 21
    assert tashkent_dt.tzinfo == TASHKENT_TZ

    # Round trip
    back_to_utc = to_utc(tashkent_dt)
    assert back_to_utc == utc_dt


def test_format_tashkent():
    utc_dt = datetime(2026, 10, 21, 7, 30, tzinfo=timezone.utc)
    formatted = format_tashkent(utc_dt, "%Y-%m-%d %H:%M")
    assert formatted == "2026-10-21 12:30"


def test_date_range_boundaries_utc():
    start_d = date(2026, 10, 1)
    end_d = date(2026, 10, 2)

    start_utc, end_utc = get_date_range_boundaries_utc(start_d, end_d)

    # 2026-10-01 00:00:00 Tashkent is 2026-09-30 19:00:00 UTC
    assert start_utc == datetime(2026, 9, 30, 19, 0, 0, tzinfo=UTC_TZ)

    # 2026-10-02 23:59:59.999999 Tashkent is 2026-10-02 18:59:59.999999 UTC
    assert end_utc.year == 2026
    assert end_utc.month == 10
    assert end_utc.day == 2
    assert end_utc.hour == 18
