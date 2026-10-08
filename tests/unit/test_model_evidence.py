from datetime import UTC, datetime, timedelta

import polars as pl

from sports_engine.training.evidence import EvidenceState, assess_model_evidence, load_evidence_policies


def _frame(rows: int, *, features: int = 2) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    values = []
    labels = ("HOME", "DRAW", "AWAY")
    for index in range(rows):
        row: dict[str, object] = {
            "fixture_id": f"fixture-{index}",
            "prediction_timestamp": start + timedelta(days=index),
            "home_team_id": f"team-{index % 12}",
            "away_team_id": f"team-{(index + 1) % 12}",
            "target_result": labels[index % 3],
        }
        row.update({f"feature_{feature}": float(index + feature) for feature in range(features)})
        values.append(row)
    return pl.DataFrame(values)


def test_evidence_is_model_specific_not_a_universal_row_gate() -> None:
    policies = load_evidence_policies()
    frame = _frame(90, features=61)
    poisson = assess_model_evidence("poisson", frame, policies["poisson"])
    catboost = assess_model_evidence(
        "catboost",
        frame,
        policies["catboost"],
        feature_columns=[f"feature_{index}" for index in range(61)],
    )
    assert poisson.state in {EvidenceState.RESEARCH_TRAINABLE, EvidenceState.VALIDATION_ELIGIBLE}
    assert catboost.state == EvidenceState.INSUFFICIENT_DATA
    assert "INSUFFICIENT_ROWS_PER_FEATURE" in catboost.reasons


def test_evidence_progresses_without_becoming_actionable_early() -> None:
    policy = load_evidence_policies()["poisson"]
    research = assess_model_evidence("poisson", _frame(60), policy)
    validation = assess_model_evidence("poisson", _frame(220), policy)
    candidate = assess_model_evidence("poisson", _frame(220), policy, evaluation_passed=True)
    assert research.state == EvidenceState.RESEARCH_TRAINABLE
    assert validation.state == EvidenceState.VALIDATION_ELIGIBLE
    assert candidate.state == EvidenceState.PRODUCTION_ACTIONABLE


def test_ml_requires_calibration_after_successful_evaluation() -> None:
    policy = load_evidence_policies()["logistic"]
    frame = _frame(420, features=100)
    features = [f"feature_{index}" for index in range(100)]
    candidate = assess_model_evidence("logistic", frame, policy, feature_columns=features, evaluation_passed=True)
    actionable = assess_model_evidence(
        "logistic",
        frame,
        policy,
        feature_columns=features,
        evaluation_passed=True,
        calibrated=True,
    )
    assert candidate.state == EvidenceState.PRODUCTION_CANDIDATE
    assert candidate.reasons == ("CALIBRATION_REQUIRED",)
    assert actionable.state == EvidenceState.PRODUCTION_ACTIONABLE


def test_ml_rejects_a_constant_feature_matrix() -> None:
    frame = _frame(120, features=0).with_columns(pl.lit(1.0).alias("constant"))
    assessment = assess_model_evidence(
        "logistic",
        frame,
        load_evidence_policies()["logistic"],
        feature_columns=["constant"],
    )
    assert assessment.state == EvidenceState.INSUFFICIENT_DATA
    assert "NO_INFORMATIVE_MODEL_FEATURES" in assessment.reasons
