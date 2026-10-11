import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

MODEL_TYPES = ("elo", "poisson", "dixon-coles", "logistic", "catboost", "lightgbm")
MODEL_STATUSES = ("candidate", "champion", "retired", "rejected")


def validate_model_type(model_type: str) -> str:
    if model_type not in MODEL_TYPES:
        raise ValueError(f"Unknown model {model_type!r}; choose from {', '.join(MODEL_TYPES)}")
    return model_type


@dataclass(frozen=True, slots=True)
class ModelRun:
    model_type: str
    version: str
    status: str
    training_start: datetime
    training_end: datetime
    feature_schema_hash: str
    training_dataset_hash: str
    hyperparameters: dict[str, Any]
    metrics: dict[str, Any]
    calibration_method: str | None
    artifact_path: Path
    library_versions: dict[str, str]
    git_commit: str | None
    created_at: datetime


class ModelRegistry:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def register(self, run: ModelRun) -> str:
        validate_model_type(run.model_type)
        if run.status not in MODEL_STATUSES:
            raise ValueError(f"Invalid model status {run.status!r}")
        model_run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-engine:model:{run.version}"))
        self.connection.execute(
            "INSERT INTO model_runs (model_run_id, model_type, version, status, training_start, training_end, "
            "feature_schema_hash, training_dataset_hash, hyperparameters, metrics, calibration_method, artifact_path, "
            "library_versions, git_commit, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                model_run_id,
                run.model_type,
                run.version,
                run.status,
                run.training_start,
                run.training_end,
                run.feature_schema_hash,
                run.training_dataset_hash,
                json.dumps(run.hyperparameters, sort_keys=True),
                json.dumps(run.metrics, sort_keys=True),
                run.calibration_method,
                str(run.artifact_path),
                json.dumps(run.library_versions, sort_keys=True),
                run.git_commit,
                run.created_at,
            ],
        )
        return model_run_id

    def promote(self, version: str) -> None:
        row = self.connection.execute(
            "SELECT metrics, evidence_state FROM model_runs WHERE version=? AND status='candidate'", [version]
        ).fetchone()
        if not row:
            raise ValueError(f"Candidate model {version!r} does not exist")
        candidate_metrics = self._metrics(row[0])
        if row[1] != "PRODUCTION_ACTIONABLE":
            state = row[1] if row[1] is not None else "UNASSESSED"
            raise ValueError(f"Candidate evidence state {state} is not production-actionable")
        baseline = candidate_metrics.get("bookmaker_baseline")
        if isinstance(baseline, dict) and not self._is_better(candidate_metrics, baseline):
            raise ValueError("Candidate does not outperform the bookmaker baseline on probability metrics")
        champion = self.connection.execute(
            "SELECT metrics FROM model_runs WHERE status='champion' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if champion and not self._is_better(candidate_metrics, self._metrics(champion[0])):
            raise ValueError("Candidate does not improve the current champion probability metrics")
        self.connection.begin()
        try:
            self.connection.execute("UPDATE model_runs SET status='retired' WHERE status='champion'")
            self.connection.execute("UPDATE model_runs SET status='champion' WHERE version=?", [version])
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def reject(self, version: str) -> None:
        changed = self.connection.execute(
            "UPDATE model_runs SET status='rejected' WHERE version=? AND status='candidate' RETURNING version",
            [version],
        ).fetchone()
        if not changed:
            raise ValueError(f"Candidate model {version!r} does not exist")

    @staticmethod
    def _metrics(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else json.loads(value)

    @staticmethod
    def _is_better(candidate: dict[str, Any], benchmark: dict[str, Any]) -> bool:
        try:
            return float(candidate["log_loss"]) < float(benchmark["log_loss"]) and float(candidate["brier"]) <= float(
                benchmark["brier"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Promotion requires log_loss and brier metrics") from exc
