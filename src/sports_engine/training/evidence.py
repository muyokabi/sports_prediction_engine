import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import yaml

from sports_engine.core.paths import project_root
from sports_engine.training.temporal_split import split_by_time


class EvidenceState(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    RESEARCH_TRAINABLE = "RESEARCH_TRAINABLE"
    VALIDATION_ELIGIBLE = "VALIDATION_ELIGIBLE"
    PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"
    PRODUCTION_ACTIONABLE = "PRODUCTION_ACTIONABLE"


@dataclass(frozen=True, slots=True)
class ModelEvidencePolicy:
    research_rows: int
    validation_rows: int
    test_rows: int
    minimum_teams: int
    minimum_chronological_folds: int
    production_validation_rows: int
    production_test_rows: int
    calibration_rows: int
    maximum_missing_fraction: float
    rows_per_feature: float
    maximum_log_loss: float
    maximum_brier: float
    minimum_class_rows: int = 0


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    model_type: str
    state: EvidenceState
    reasons: tuple[str, ...]
    measurements: dict[str, Any]
    policy: ModelEvidencePolicy


def load_evidence_policies(path: Path | None = None) -> dict[str, ModelEvidencePolicy]:
    requested = path or project_root() / "config" / "models" / "evidence.yaml"
    payload = yaml.safe_load(requested.read_text(encoding="utf-8"))
    return {name: ModelEvidencePolicy(**values) for name, values in payload["policies"].items()}


def assess_model_evidence(
    model_type: str,
    frame: pl.DataFrame,
    policy: ModelEvidencePolicy,
    *,
    feature_columns: list[str] | None = None,
    calibrated: bool = False,
    evaluation_passed: bool = False,
) -> EvidenceAssessment:
    times = frame["prediction_timestamp"].to_list()
    fold = split_by_time(times)
    targets = frame["target_result"].to_list()
    class_counts = {str(label): targets.count(label) for label in sorted(set(targets))}
    team_count = len(set(frame["home_team_id"].to_list()) | set(frame["away_team_id"].to_list()))
    features = feature_columns or []
    normalized_features = {
        name: frame[name].fill_nan(None) if frame.schema[name].is_float() else frame[name] for name in features
    }
    informative_features = [name for name, series in normalized_features.items() if series.drop_nulls().n_unique() > 1]
    missing = (
        sum(series.null_count() for series in normalized_features.values()) / (frame.height * len(features))
        if features and frame.height
        else 0.0
    )
    distinct_times = len(set(times))
    possible_folds = max(0, distinct_times // max(1, policy.test_rows))
    measurements: dict[str, Any] = {
        "total_rows": frame.height,
        "unique_fixtures": frame["fixture_id"].n_unique() if "fixture_id" in frame.columns else frame.height,
        "unique_teams": team_count,
        "class_counts": class_counts,
        "train_rows": len(fold.train),
        "validation_rows": len(fold.validation),
        "test_rows": len(fold.test),
        "chronological_folds_possible": possible_folds,
        "feature_count": len(features),
        "informative_feature_count": len(informative_features),
        "constant_feature_count": len(features) - len(informative_features),
        "rows_per_feature": frame.height / len(features) if features else None,
        "missing_fraction": missing,
        "calibrated": calibrated,
        "evaluation_passed": evaluation_passed,
    }
    research_reasons: list[str] = []
    if frame.height < policy.research_rows:
        research_reasons.append("INSUFFICIENT_RESEARCH_ROWS")
    if team_count < policy.minimum_teams:
        research_reasons.append("INSUFFICIENT_TEAM_REPRESENTATION")
    if policy.minimum_class_rows and min(class_counts.values(), default=0) < policy.minimum_class_rows:
        research_reasons.append("INSUFFICIENT_CLASS_SUPPORT")
    if missing > policy.maximum_missing_fraction:
        research_reasons.append("EXCESSIVE_FEATURE_MISSINGNESS")
    if features and not informative_features:
        research_reasons.append("NO_INFORMATIVE_MODEL_FEATURES")
    if features and policy.rows_per_feature and frame.height / len(features) < policy.rows_per_feature:
        research_reasons.append("INSUFFICIENT_ROWS_PER_FEATURE")
    if research_reasons:
        return EvidenceAssessment(
            model_type, EvidenceState.INSUFFICIENT_DATA, tuple(research_reasons), measurements, policy
        )

    validation_reasons: list[str] = []
    if len(fold.validation) < policy.validation_rows or len(fold.test) < policy.test_rows:
        validation_reasons.append("INSUFFICIENT_VALIDATION_HISTORY")
    if possible_folds < policy.minimum_chronological_folds:
        validation_reasons.append("INSUFFICIENT_CHRONOLOGICAL_FOLDS")
    if validation_reasons:
        return EvidenceAssessment(
            model_type,
            EvidenceState.RESEARCH_TRAINABLE,
            tuple(validation_reasons),
            measurements,
            policy,
        )

    production_reasons: list[str] = []
    if len(fold.validation) < policy.production_validation_rows or len(fold.test) < policy.production_test_rows:
        production_reasons.append("INSUFFICIENT_PRODUCTION_HOLDOUT")
    if not evaluation_passed:
        production_reasons.append("CHRONOLOGICAL_EVALUATION_REQUIRED")
    if production_reasons:
        return EvidenceAssessment(
            model_type,
            EvidenceState.VALIDATION_ELIGIBLE,
            tuple(production_reasons),
            measurements,
            policy,
        )
    if policy.calibration_rows and (len(fold.validation) < policy.calibration_rows or not calibrated):
        return EvidenceAssessment(
            model_type,
            EvidenceState.PRODUCTION_CANDIDATE,
            (
                "INSUFFICIENT_CALIBRATION_SAMPLE"
                if len(fold.validation) < policy.calibration_rows
                else "CALIBRATION_REQUIRED",
            ),
            measurements,
            policy,
        )
    return EvidenceAssessment(model_type, EvidenceState.PRODUCTION_ACTIONABLE, (), measurements, policy)


def persist_evidence_assessment(
    connection: duckdb.DuckDBPyConnection,
    assessment: EvidenceAssessment,
    *,
    dataset_id: str,
    model_version: str | None = None,
) -> str:
    assessment_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO model_evidence_assessments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            assessment_id,
            assessment.model_type,
            dataset_id,
            model_version,
            assessment.state,
            json.dumps(assessment.reasons),
            json.dumps(assessment.measurements, default=str),
            json.dumps(asdict(assessment.policy)),
            datetime.now(UTC),
        ],
    )
    return assessment_id
