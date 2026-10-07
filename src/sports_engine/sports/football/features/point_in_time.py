from collections.abc import Iterable
from datetime import datetime

from sports_engine.core.exceptions import LeakageError


def require_known_before(prediction_timestamp: datetime, observed_timestamps: Iterable[datetime | None]) -> None:
    violations = [stamp for stamp in observed_timestamps if stamp is None or stamp > prediction_timestamp]
    if violations:
        raise LeakageError(f"{len(violations)} source observations are unknown or later than prediction timestamp")


def sql_cutoff(column: str = "retrieved_at") -> str:
    allowed = {"retrieved_at", "observed_at", "kickoff_utc"}
    if column not in allowed:
        raise ValueError(f"Unsupported cutoff column: {column}")
    return f"{column} <= ?"
