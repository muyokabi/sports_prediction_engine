from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_date(timezone: str, *, now: datetime | None = None) -> date:
    instant = now or utc_now()
    return instant.astimezone(ZoneInfo(timezone)).date()


def target_date(timezone: str, days_ahead: int, *, now: datetime | None = None) -> date:
    return local_date(timezone, now=now) + timedelta(days=days_ahead)
