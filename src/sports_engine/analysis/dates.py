from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class AnalysisDateRange:
    start: date
    end: date

    @property
    def dates(self) -> tuple[date, ...]:
        return tuple(self.start + timedelta(days=offset) for offset in range((self.end - self.start).days + 1))


def resolve_analysis_dates(
    value: str,
    *,
    timezone: str,
    days: int = 1,
    now: datetime | None = None,
) -> AnalysisDateRange:
    if days < 1:
        raise ValueError("days must be at least one")
    local_today = (now or datetime.now(ZoneInfo(timezone))).astimezone(ZoneInfo(timezone)).date()
    normalized = value.strip().lower()
    if normalized == "today":
        start = local_today
    elif normalized == "tomorrow":
        start = local_today + timedelta(days=1)
    else:
        start = date.fromisoformat(value)
    return AnalysisDateRange(start, start + timedelta(days=days - 1))
