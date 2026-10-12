import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import duckdb


class UpdateTrigger(StrEnum):
    NEW_OBSERVATIONS = "NEW_OBSERVATIONS"
    ELAPSED_TIME = "ELAPSED_TIME"
    DRIFT = "DRIFT"
    CALIBRATION = "CALIBRATION"
    LEAGUE_EXPANSION = "LEAGUE_EXPANSION"
    FEATURE_SCHEMA = "FEATURE_SCHEMA"


@dataclass(frozen=True, slots=True)
class RetrainingPolicy:
    minimum_new_observations: int
    maximum_age: timedelta
    mode: str


@dataclass(frozen=True, slots=True)
class UpdateDecision:
    model_type: str
    current_version: str | None
    due: bool
    observations_since_training: int
    triggers: tuple[UpdateTrigger, ...]
    mode: str


DEFAULT_RETRAINING_POLICIES = {
    "elo": RetrainingPolicy(1, timedelta(days=1), "full_refit"),
    "poisson": RetrainingPolicy(20, timedelta(days=7), "full_refit"),
    "dixon-coles": RetrainingPolicy(20, timedelta(days=7), "full_refit"),
    # Full refits are intentionally the automatic policy for ML models. The
    # training set is small enough for CPU refits, while appending a complete
    # 300-tree learner to batches of roughly 50 observations caused model size
    # to grow without bound and degraded chronological holdout scores. Manual
    # warm-start candidates remain available for controlled experiments.
    "logistic": RetrainingPolicy(40, timedelta(days=14), "full_refit"),
    "catboost": RetrainingPolicy(60, timedelta(days=14), "full_refit"),
    "lightgbm": RetrainingPolicy(60, timedelta(days=14), "full_refit"),
}


def assess_model_update(
    connection: duckdb.DuckDBPyConnection,
    model_type: str,
    *,
    eligible_observations: int,
    now: datetime | None = None,
    drift: bool = False,
    calibration_due: bool = False,
    league_expanded: bool = False,
    feature_schema_changed: bool = False,
) -> UpdateDecision:
    policy = DEFAULT_RETRAINING_POLICIES[model_type]
    observed = now or datetime.now(UTC)
    row = connection.execute(
        "SELECT version, observations_included, created_at FROM model_runs WHERE model_type=? "
        "ORDER BY created_at DESC LIMIT 1",
        [model_type],
    ).fetchone()
    version = str(row[0]) if row else None
    included = int(row[1] or 0) if row else 0
    new_count = max(0, eligible_observations - included)
    triggers: list[UpdateTrigger] = []
    # A missing model means that an initial fit is needed only after at least
    # one eligible observation exists.  Treating an empty, freshly migrated
    # warehouse as NEW_OBSERVATIONS makes the daily workflow try to build an
    # impossible empty feature dataset.
    if (row is None and eligible_observations > 0) or new_count >= policy.minimum_new_observations:
        triggers.append(UpdateTrigger.NEW_OBSERVATIONS)
    if row and observed - row[2] >= policy.maximum_age:
        triggers.append(UpdateTrigger.ELAPSED_TIME)
    if drift:
        triggers.append(UpdateTrigger.DRIFT)
    if calibration_due:
        triggers.append(UpdateTrigger.CALIBRATION)
    if league_expanded:
        triggers.append(UpdateTrigger.LEAGUE_EXPANSION)
    if feature_schema_changed:
        triggers.append(UpdateTrigger.FEATURE_SCHEMA)
    decision = UpdateDecision(model_type, version, bool(triggers), new_count, tuple(triggers), policy.mode)
    connection.execute(
        "INSERT INTO model_update_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            str(uuid.uuid4()),
            model_type,
            version,
            triggers[0] if triggers else "NONE",
            new_count,
            bool(triggers),
            json.dumps(triggers),
            observed,
        ],
    )
    return decision
