from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


def _integer(headers: Mapping[str, str], name: str) -> int | None:
    value = headers.get(name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class QuotaObservation:
    daily_limit: int | None
    daily_remaining: int | None
    minute_limit: int | None
    minute_remaining: int | None
    observed_at: datetime

    @classmethod
    def from_headers(cls, headers: Mapping[str, str], observed_at: datetime) -> "QuotaObservation":
        lowered = {key.lower(): value for key, value in headers.items()}
        return cls(
            _integer(lowered, "x-ratelimit-requests-limit"),
            _integer(lowered, "x-ratelimit-requests-remaining"),
            _integer(lowered, "x-ratelimit-limit"),
            _integer(lowered, "x-ratelimit-remaining"),
            observed_at,
        )
