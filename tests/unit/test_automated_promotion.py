import json
import pickle
from datetime import UTC, datetime
from pathlib import Path

from sports_engine.core.config import AppConfig
from sports_engine.models.registry import ModelRegistry, ModelRun
from sports_engine.models.serialization import save_pickle, write_artifact_metadata
from sports_engine.training.promotion import run_automated_promotion
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def _candidate(connection: object, tmp_path: Path, *, with_baseline: bool) -> str:
    version = "logistic-production-candidate"
    metrics = {
        "log_loss": 0.90,
        "brier": 0.55,
        "rps": 0.19,
        "expected_calibration_error": 0.03,
        "uncalibrated": {"expected_calibration_error": 0.04},
        "test_rows": 250,
    }
    if with_baseline:
        metrics["bookmaker_baseline"] = {"log_loss": 1.05, "brier": 0.64, "rows": 250}
    now = datetime(2026, 1, 1, tzinfo=UTC)
    artifact_path = tmp_path / "model.pkl"
    save_pickle({"model": "candidate"}, artifact_path, {"kind": "test"})
    (tmp_path / "calibrator.pkl").write_bytes(pickle.dumps({"calibrator": "test"}))
    write_artifact_metadata(artifact_path, {"kind": "test"})
    ModelRegistry(connection).register(
        ModelRun(
            model_type="logistic",
            version=version,
            status="candidate",
            training_start=now,
            training_end=now,
            feature_schema_hash="schema",
            training_dataset_hash="promotion-dataset-hash",
            hyperparameters={},
            metrics=metrics,
            calibration_method="platt",
            artifact_path=artifact_path,
            library_versions={},
            git_commit=None,
            created_at=now,
        )
    )
    connection.execute(
        "UPDATE model_runs SET evidence_state='PRODUCTION_ACTIONABLE', training_mode='full_refit' WHERE version=?",
        [version],
    )
    return version


def _deterministic_champion(connection: object, tmp_path: Path) -> str:
    version = "poisson-fundamental-champion"
    now = datetime(2025, 12, 1, tzinfo=UTC)
    ModelRegistry(connection).register(
        ModelRun(
            model_type="poisson",
            version=version,
            status="champion",
            training_start=now,
            training_end=now,
            feature_schema_hash="schema",
            training_dataset_hash="fundamental-dataset-hash",
            hyperparameters={},
            metrics={"log_loss": 1.0, "brier": 0.60},
            calibration_method=None,
            artifact_path=tmp_path / "poisson.pkl",
            library_versions={},
            git_commit=None,
            created_at=now,
        )
    )
    connection.execute(
        "UPDATE model_runs SET evidence_state='PRODUCTION_ACTIONABLE' WHERE version=?",
        [version],
    )
    return version


def _report(tmp_path: Path) -> None:
    output = tmp_path / "evaluation"
    output.mkdir()
    payload = {
        "model_type": "logistic",
        "candidate_version": "logistic-production-candidate",
        "dataset_hash": "promotion-dataset-hash",
        "created_at": "2026-01-02T00:00:00+00:00",
        "fold_metrics": [{"expected_calibration_error": 0.04}] * 4,
        "aggregate_metrics": {
            "folds": 4,
            "test_rows": 300,
            "probability_forensics": {"passed": True, "reasons": []},
            "metric_uncertainty": {
                "log_loss": {"estimate": 0.90, "lower": 0.87, "upper": 0.94},
                "brier": {"estimate": 0.55, "lower": 0.52, "upper": 0.58},
                "rps": {"estimate": 0.19, "lower": 0.17, "upper": 0.21},
            },
            "bookmaker_baseline": {"log_loss": 1.05, "brier": 0.64, "rows": 300},
            "paired_market_difference": {
                "log_loss": {"estimate": -0.15, "lower": -0.20, "upper": -0.08},
                "brier": {"estimate": -0.09, "lower": -0.13, "upper": -0.04},
            },
        },
    }
    (output / "logistic-promotion-da-report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_automated_promotion_grants_audited_market_role(tmp_path: Path) -> None:
    connection = connect(tmp_path / "promotion.duckdb")
    migrate(connection)
    fundamental = _deterministic_champion(connection, tmp_path)
    version = _candidate(connection, tmp_path, with_baseline=True)
    _report(tmp_path)
    config = AppConfig(artifacts_dir=tmp_path)

    result = run_automated_promotion(connection, config, now=datetime(2026, 1, 3, tzinfo=UTC))

    assert result.promoted_versions == (version,)
    row = connection.execute("SELECT status, metrics FROM model_runs WHERE version=?", [version]).fetchone()
    assert row[0] == "champion"
    assert connection.execute("SELECT status FROM model_runs WHERE version=?", [fundamental]).fetchone() == (
        "champion",
    )
    metrics = json.loads(row[1])
    assert metrics["uncertainty_policy"]["validated"] is True
    assert metrics["minimum_odds_policy"]["validated"] is True
    assert connection.execute(
        "SELECT state FROM calibration_validations WHERE model_version=?", [version]
    ).fetchone() == ("CALIBRATION_VALIDATED",)
    assert connection.execute("SELECT state FROM model_market_roles WHERE model_version=?", [version]).fetchone() == (
        "CHAMPION",
    )
    assert connection.execute(
        "SELECT state FROM model_promotion_assessments WHERE model_version=?", [version]
    ).fetchone() == ("PROMOTED",)
    connection.close()


def test_automated_promotion_withholds_without_market_baseline(tmp_path: Path) -> None:
    connection = connect(tmp_path / "withheld.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    _report(tmp_path)
    config = AppConfig(artifacts_dir=tmp_path)

    result = run_automated_promotion(connection, config, now=datetime(2026, 1, 3, tzinfo=UTC))

    assert result.promoted_versions == ()
    assert result.withheld_versions == (version,)
    assert connection.execute("SELECT status FROM model_runs WHERE version=?", [version]).fetchone() == ("candidate",)
    reasons = json.loads(
        connection.execute(
            "SELECT reason_codes FROM model_promotion_assessments WHERE model_version=?", [version]
        ).fetchone()[0]
    )
    assert "INSUFFICIENT_POINT_IN_TIME_MARKET_BASELINE" in reasons
    assert "BOOKMAKER_BASELINE_NOT_OUTPERFORMED" not in reasons
    connection.close()


def test_when_available_policy_requires_baseline_when_significant_outperformance_is_required(tmp_path: Path) -> None:
    connection = connect(tmp_path / "available-policy.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    _report(tmp_path)
    config = AppConfig(
        artifacts_dir=tmp_path,
        models={
            "promotion": {
                "market_baseline_mode": "when_available",
                "eligible_model_types": ["logistic"],
            }
        },
    )

    result = run_automated_promotion(connection, config, now=datetime(2026, 1, 3, tzinfo=UTC))

    assert result.promoted_versions == ()
    assert result.withheld_versions == (version,)
    assessment = result.assessments[0]
    assert assessment.gate_results["market_baseline"]["passed"] is False
    assert assessment.gate_results["market_baseline"]["available"] is False
    assert assessment.gate_results["market_baseline"]["required"] is True
    assert "INSUFFICIENT_POINT_IN_TIME_MARKET_BASELINE" in assessment.reasons
    assert "BOOKMAKER_BASELINE_NOT_OUTPERFORMED" not in assessment.reasons
    connection.close()


def test_when_available_policy_can_omit_baseline_when_outperformance_is_not_required(tmp_path: Path) -> None:
    connection = connect(tmp_path / "optional-baseline-policy.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    _report(tmp_path)
    config = AppConfig(
        artifacts_dir=tmp_path,
        models={
            "promotion": {
                "market_baseline_mode": "when_available",
                "require_significant_market_outperformance": False,
                "eligible_model_types": ["logistic"],
            }
        },
    )

    result = run_automated_promotion(connection, config, now=datetime(2026, 1, 3, tzinfo=UTC))

    assert result.promoted_versions == (version,)
    assessment = result.assessments[0]
    assert assessment.gate_results["market_baseline"]["passed"] is True
    assert assessment.gate_results["market_baseline"]["available"] is False
    assert assessment.gate_results["market_baseline"]["required"] is False
    connection.close()


def test_promotion_rejects_walk_forward_report_from_another_candidate(tmp_path: Path) -> None:
    connection = connect(tmp_path / "mismatched-report.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=True)
    _report(tmp_path)
    path = next((tmp_path / "evaluation").glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["candidate_version"] = "different-candidate"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = run_automated_promotion(connection, AppConfig(artifacts_dir=tmp_path))

    assert result.promoted_versions == ()
    assert result.withheld_versions == (version,)
    assert "WALK_FORWARD_REPORT_MISSING" in result.assessments[0].reasons
    connection.close()


def test_promotion_rejects_incremental_artifact_even_with_passing_report(tmp_path: Path) -> None:
    connection = connect(tmp_path / "incremental-protocol.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    connection.execute("UPDATE model_runs SET training_mode='warm_start' WHERE version=?", [version])
    _report(tmp_path)
    config = AppConfig(
        artifacts_dir=tmp_path,
        models={
            "promotion": {
                "market_baseline_mode": "when_available",
                "require_significant_market_outperformance": False,
                "eligible_model_types": ["logistic"],
            }
        },
    )

    result = run_automated_promotion(connection, config)

    assert result.promoted_versions == ()
    assert "TRAINING_PROTOCOL_NOT_PROMOTION_ELIGIBLE" in result.assessments[0].reasons
    assert result.assessments[0].gate_results["training_protocol"] == {
        "passed": False,
        "mode": "warm_start",
        "eligible_modes": ["full_refit"],
    }
    connection.close()


def test_promotion_rejects_explicit_probability_forensics_failure(tmp_path: Path) -> None:
    connection = connect(tmp_path / "forensics-failure.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    _report(tmp_path)
    path = next((tmp_path / "evaluation").glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["aggregate_metrics"]["probability_forensics"] = {
        "passed": False,
        "reasons": ["MATERIAL_CONFIDENCE_BAND_MISCALIBRATION"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    config = AppConfig(
        artifacts_dir=tmp_path,
        models={
            "promotion": {
                "market_baseline_mode": "when_available",
                "require_significant_market_outperformance": False,
                "eligible_model_types": ["logistic"],
            }
        },
    )

    result = run_automated_promotion(connection, config)

    assert result.promoted_versions == ()
    assert result.withheld_versions == (version,)
    assert "PROBABILITY_FORENSICS_FAILED" in result.assessments[0].reasons
    assert result.assessments[0].gate_results["probability_forensics"]["evidence"]["reasons"] == [
        "MATERIAL_CONFIDENCE_BAND_MISCALIBRATION"
    ]
    connection.close()


def test_promotion_rejects_hashless_legacy_artifact(tmp_path: Path) -> None:
    connection = connect(tmp_path / "hashless-artifact.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    manifest_path = tmp_path / "model.pkl.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("artifact_sha256")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _report(tmp_path)
    config = AppConfig(
        artifacts_dir=tmp_path,
        models={
            "promotion": {
                "market_baseline_mode": "when_available",
                "require_significant_market_outperformance": False,
                "eligible_model_types": ["logistic"],
            }
        },
    )

    result = run_automated_promotion(connection, config)

    assert result.promoted_versions == ()
    assert result.withheld_versions == (version,)
    assert "ARTIFACT_INTEGRITY_NOT_VERIFIED" in result.assessments[0].reasons
    assert result.assessments[0].gate_results["artifact_integrity"]["passed"] is False
    connection.close()


def test_promotion_rejects_tampered_calibrator(tmp_path: Path) -> None:
    connection = connect(tmp_path / "tampered-calibrator.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    calibrator_path = tmp_path / "calibrator.pkl"
    payload = bytearray(calibrator_path.read_bytes())
    payload[-1] ^= 1
    calibrator_path.write_bytes(payload)
    _report(tmp_path)
    config = AppConfig(
        artifacts_dir=tmp_path,
        models={
            "promotion": {
                "market_baseline_mode": "when_available",
                "require_significant_market_outperformance": False,
                "eligible_model_types": ["logistic"],
            }
        },
    )

    result = run_automated_promotion(connection, config)

    assert result.promoted_versions == ()
    assert result.withheld_versions == (version,)
    assert "ARTIFACT_INTEGRITY_NOT_VERIFIED" in result.assessments[0].reasons
    assert "integrity check failed" in result.assessments[0].gate_results["artifact_integrity"]["error"]
    connection.close()


def test_reassessment_demotes_incumbent_when_forensics_later_fail(tmp_path: Path) -> None:
    connection = connect(tmp_path / "incumbent-reassessment.duckdb")
    migrate(connection)
    version = _candidate(connection, tmp_path, with_baseline=False)
    _report(tmp_path)
    config = AppConfig(
        artifacts_dir=tmp_path,
        models={
            "promotion": {
                "market_baseline_mode": "when_available",
                "require_significant_market_outperformance": False,
                "eligible_model_types": ["logistic"],
            }
        },
    )
    first = run_automated_promotion(connection, config, now=datetime(2026, 1, 3, tzinfo=UTC))
    assert first.promoted_versions == (version,)

    path = next((tmp_path / "evaluation").glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["aggregate_metrics"]["probability_forensics"] = {
        "passed": False,
        "reasons": ["MATERIAL_CONFIDENCE_BAND_MISCALIBRATION"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    second = run_automated_promotion(connection, config, now=datetime(2026, 1, 4, tzinfo=UTC))

    assert second.withheld_versions == (version,)
    assert connection.execute("SELECT status FROM model_runs WHERE version=?", [version]).fetchone() == ("candidate",)
    assert connection.execute("SELECT state FROM model_market_roles WHERE model_version=?", [version]).fetchone() == (
        "CHALLENGER",
    )
    assert connection.execute("SELECT count(*) FROM model_market_roles WHERE state='CHAMPION'").fetchone() == (0,)
    connection.close()
