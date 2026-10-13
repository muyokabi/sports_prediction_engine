import json
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from sports_engine.core.config import AppConfig, ModelPromotionConfig
from sports_engine.models.serialization import verify_artifact_digest
from sports_engine.training.evidence import load_evidence_policies

ML_MODEL_TYPES = ("logistic", "catboost", "lightgbm")
SCORE_MODEL_TYPES = ("poisson", "dixon-coles")
PROMOTION_MODEL_TYPES = (*SCORE_MODEL_TYPES, *ML_MODEL_TYPES)


@dataclass(frozen=True, slots=True)
class PromotionAssessment:
    version: str
    model_type: str
    market_family: str
    state: str
    reasons: tuple[str, ...]
    gate_results: dict[str, Any]
    evaluation_path: Path | None


@dataclass(frozen=True, slots=True)
class PromotionCycleResult:
    assessed_versions: tuple[str, ...]
    promoted_versions: tuple[str, ...]
    withheld_versions: tuple[str, ...]
    assessments: tuple[PromotionAssessment, ...]


def run_automated_promotion(
    connection: duckdb.DuckDBPyConnection,
    config: AppConfig,
    *,
    versions: tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> PromotionCycleResult:
    """Evaluate probability candidates and atomically grant a market-specific role.

    A role is granted only when the configured evidence policy passes. Historical
    bookmaker comparison is enforced whenever point-in-time API-Football evidence
    exists. A ``when_available`` policy can omit that gate only when significant
    market outperformance is not itself configured as a promotion requirement.
    """
    policy = config.models.promotion
    if not policy.enabled:
        return PromotionCycleResult((), (), (), ())
    parameters: list[Any] = [policy.market_family, *PROMOTION_MODEL_TYPES]
    version_clause = ""
    if versions:
        version_clause = f" AND version IN ({','.join('?' for _ in versions)})"
        parameters.extend(versions)
    rows = connection.execute(
        "SELECT version, model_type, metrics, calibration_method, training_dataset_hash, evidence_state, "
        "coalesce(training_mode, 'unknown'), artifact_path "
        "FROM model_runs WHERE (status='candidate' OR (status='champion' AND EXISTS ("
        "SELECT 1 FROM model_market_roles r WHERE r.model_version=model_runs.version "
        "AND r.market_family=? AND r.state='CHAMPION'))) AND model_type IN "
        f"({','.join('?' for _ in PROMOTION_MODEL_TYPES)})"
        f"{version_clause} ORDER BY created_at",
        parameters,
    ).fetchall()
    assessments = tuple(
        _assess_candidate(
            connection,
            config.artifacts_dir / "evaluation",
            policy,
            version=str(row[0]),
            model_type=str(row[1]),
            metrics=_mapping(row[2]),
            calibration_method=str(row[3]) if row[3] else None,
            dataset_hash=str(row[4]),
            evidence_state=str(row[5]) if row[5] else None,
            training_mode=str(row[6]),
            artifact_path=Path(str(row[7])),
            assessed_at=now or datetime.now(UTC),
        )
        for row in rows
    )
    promoted = tuple(item.version for item in assessments if item.state == "PROMOTED")
    withheld = tuple(item.version for item in assessments if item.state == "WITHHELD")
    return PromotionCycleResult(
        tuple(item.version for item in assessments),
        promoted,
        withheld,
        assessments,
    )


def _assess_candidate(
    connection: duckdb.DuckDBPyConnection,
    evaluation_dir: Path,
    policy: ModelPromotionConfig,
    *,
    version: str,
    model_type: str,
    metrics: dict[str, Any],
    calibration_method: str | None,
    dataset_hash: str,
    evidence_state: str | None,
    training_mode: str,
    artifact_path: Path,
    assessed_at: datetime,
) -> PromotionAssessment:
    report_path, report = _latest_report(evaluation_dir, model_type, dataset_hash, version)
    aggregate = _mapping(report.get("aggregate_metrics")) if report else {}
    evidence_policy = load_evidence_policies()[model_type]
    reasons: list[str] = []

    artifact_integrity_passed = True
    artifact_integrity_error: str | None = None
    manifest_path = artifact_path.with_suffix(artifact_path.suffix + ".json")
    try:
        verify_artifact_digest(artifact_path, require_digest=True)
        if calibration_method:
            verify_artifact_digest(
                artifact_path.parent / "calibrator.pkl",
                metadata_path=manifest_path,
                hash_field="calibrator_sha256",
                require_digest=True,
            )
    except (OSError, ValueError) as exc:
        artifact_integrity_passed = False
        artifact_integrity_error = str(exc)
        reasons.append("ARTIFACT_INTEGRITY_NOT_VERIFIED")

    # Walk-forward reports reconstruct a fresh candidate for every historical
    # fold. They are valid promotion evidence for full refits, but cannot prove
    # the behaviour of an incrementally extended tree ensemble. Keep manual
    # warm starts available as research artifacts and fail them closed here.
    training_protocol_passed = training_mode == "full_refit"
    if not training_protocol_passed:
        reasons.append("TRAINING_PROTOCOL_NOT_PROMOTION_ELIGIBLE")

    deployment_model_passed = model_type in policy.eligible_model_types
    if not deployment_model_passed:
        reasons.append("MODEL_TYPE_NOT_ELIGIBLE_FOR_MARKET_ROLE")

    evidence_passed = evidence_state == "PRODUCTION_ACTIONABLE"
    if not evidence_passed:
        reasons.append("EVIDENCE_NOT_PRODUCTION_ACTIONABLE")

    calibrated_ece = _number(metrics.get("expected_calibration_error"))
    uncalibrated = _mapping(metrics.get("uncalibrated"))
    uncalibrated_ece = _number(uncalibrated.get("expected_calibration_error"))
    calibration_rows = int(_number(metrics.get("test_rows")) or 0)
    calibration_passed = True
    if evidence_policy.calibration_rows and calibration_method not in {"platt", "isotonic"}:
        calibration_passed = False
        reasons.append("CALIBRATOR_MISSING")
    if calibration_rows < evidence_policy.calibration_rows:
        calibration_passed = False
        reasons.append("INSUFFICIENT_CALIBRATION_ROWS")
    if calibrated_ece is None or calibrated_ece > policy.maximum_expected_calibration_error:
        calibration_passed = False
        reasons.append("CALIBRATION_ECE_EXCEEDED")
    if (
        calibrated_ece is not None
        and uncalibrated_ece is not None
        and calibrated_ece > uncalibrated_ece + policy.maximum_calibration_regression
    ):
        calibration_passed = False
        reasons.append("CALIBRATION_REGRESSED")

    uncertainty = _mapping(aggregate.get("metric_uncertainty"))
    log_interval = _mapping(uncertainty.get("log_loss"))
    brier_interval = _mapping(uncertainty.get("brier"))
    rps_interval = _mapping(uncertainty.get("rps"))
    folds = int(_number(aggregate.get("folds")) or 0)
    evaluation_rows = int(_number(aggregate.get("test_rows")) or 0)
    fold_eces = (
        [
            value
            for item in report.get("fold_metrics", [])
            if isinstance(item, dict)
            if (value := _number(item.get("expected_calibration_error"))) is not None
        ]
        if report
        else []
    )
    log_upper = _number(log_interval.get("upper"))
    brier_upper = _number(brier_interval.get("upper"))
    rps_upper = _number(rps_interval.get("upper"))
    uncertainty_passed = report is not None
    if report is None:
        reasons.append("WALK_FORWARD_REPORT_MISSING")
    if folds < policy.minimum_walk_forward_folds:
        uncertainty_passed = False
        reasons.append("INSUFFICIENT_WALK_FORWARD_FOLDS")
    if evaluation_rows < policy.minimum_evaluation_rows:
        uncertainty_passed = False
        reasons.append("INSUFFICIENT_WALK_FORWARD_ROWS")
    if log_upper is None or log_upper > evidence_policy.maximum_log_loss:
        uncertainty_passed = False
        reasons.append("LOG_LOSS_UNCERTAINTY_EXCEEDED")
    if brier_upper is None or brier_upper > evidence_policy.maximum_brier:
        uncertainty_passed = False
        reasons.append("BRIER_UNCERTAINTY_EXCEEDED")
    if rps_upper is None or rps_upper > policy.maximum_rps_upper_bound:
        uncertainty_passed = False
        reasons.append("RPS_UNCERTAINTY_EXCEEDED")
    if not fold_eces or max(fold_eces) > policy.maximum_fold_expected_calibration_error:
        uncertainty_passed = False
        reasons.append("FOLD_CALIBRATION_UNSTABLE")

    probability_forensics = _mapping(aggregate.get("probability_forensics"))
    probability_forensics_passed = probability_forensics.get("passed") is True
    if not probability_forensics:
        reasons.append("PROBABILITY_FORENSICS_MISSING")
    elif not probability_forensics_passed:
        reasons.append("PROBABILITY_FORENSICS_FAILED")

    uncertainty_adjustment = _uncertainty_adjustment(policy, calibrated_ece, log_interval)
    if uncertainty_adjustment > policy.maximum_uncertainty_adjustment:
        uncertainty_passed = False
        reasons.append("UNCERTAINTY_ADJUSTMENT_EXCEEDED")

    candidate_baseline = _mapping(metrics.get("bookmaker_baseline"))
    report_baseline = _mapping(aggregate.get("bookmaker_baseline"))
    paired = _mapping(aggregate.get("paired_market_difference"))
    baseline_rows = min(
        int(_number(candidate_baseline.get("rows")) or 0),
        int(_number(report_baseline.get("rows")) or 0),
    )
    baseline_available = baseline_rows >= policy.minimum_baseline_rows
    baseline_required = policy.market_baseline_mode == "required" or policy.require_significant_market_outperformance
    baseline_passed = baseline_available or not baseline_required
    if not baseline_available and baseline_required:
        reasons.append("INSUFFICIENT_POINT_IN_TIME_MARKET_BASELINE")
    if baseline_available and not _better(metrics, candidate_baseline):
        baseline_passed = False
        reasons.append("BOOKMAKER_BASELINE_NOT_OUTPERFORMED")
    if baseline_available and policy.require_significant_market_outperformance:
        paired_log_upper = _number(_mapping(paired.get("log_loss")).get("upper"))
        paired_brier_upper = _number(_mapping(paired.get("brier")).get("upper"))
        if paired_log_upper is None or paired_log_upper >= 0:
            baseline_passed = False
            reasons.append("LOG_LOSS_MARKET_ADVANTAGE_NOT_SIGNIFICANT")
        if paired_brier_upper is None or paired_brier_upper > 0:
            baseline_passed = False
            reasons.append("BRIER_MARKET_ADVANTAGE_NOT_SIGNIFICANT")

    incumbent_version, incumbent_metrics = _incumbent(connection, policy.market_family, version)
    # A chronologically newer refit with numerically equivalent holdout quality
    # may supersede the incumbent. This matters when the new immutable artifact
    # adds validated applicability metadata without changing fitted parameters.
    incumbent_passed = incumbent_version is None or _not_worse(metrics, incumbent_metrics)
    if not incumbent_passed:
        reasons.append("INCUMBENT_NOT_OUTPERFORMED")

    gates: dict[str, Any] = {
        "artifact_integrity": {
            "passed": artifact_integrity_passed,
            "artifact_path": str(artifact_path),
            "manifest_path": str(manifest_path),
            "error": artifact_integrity_error,
        },
        "training_protocol": {
            "passed": training_protocol_passed,
            "mode": training_mode,
            "eligible_modes": ["full_refit"],
        },
        "deployment_model": {
            "passed": deployment_model_passed,
            "model_type": model_type,
            "eligible_model_types": policy.eligible_model_types,
        },
        "evidence": {"passed": evidence_passed, "state": evidence_state},
        "calibration": {
            "passed": calibration_passed,
            "method": calibration_method,
            "rows": calibration_rows,
            "ece": calibrated_ece,
            "uncalibrated_ece": uncalibrated_ece,
        },
        "uncertainty": {
            "passed": uncertainty_passed,
            "folds": folds,
            "rows": evaluation_rows,
            "metric_intervals": uncertainty,
            "maximum_fold_ece": max(fold_eces) if fold_eces else None,
            "expected_return_adjustment": uncertainty_adjustment,
        },
        "probability_forensics": {
            "passed": probability_forensics_passed,
            "evidence": probability_forensics,
        },
        "market_baseline": {
            "passed": baseline_passed,
            "available": baseline_available,
            "required": baseline_required,
            "mode": policy.market_baseline_mode,
            "rows": baseline_rows,
            "candidate_holdout": candidate_baseline,
            "walk_forward": report_baseline,
            "paired_difference": paired,
        },
        "incumbent": {
            "passed": incumbent_passed,
            "version": incumbent_version,
            "metrics": incumbent_metrics,
        },
    }
    passed = all(bool(_mapping(item).get("passed")) for item in gates.values())
    state = "PROMOTED" if passed else "WITHHELD"
    assessment = PromotionAssessment(
        version,
        model_type,
        policy.market_family,
        state,
        tuple(dict.fromkeys(reasons)),
        gates,
        report_path,
    )
    _persist_assessment(
        connection,
        policy,
        assessment,
        metrics,
        calibration_method,
        uncertainty_adjustment,
        assessed_at,
    )
    return assessment


def _persist_assessment(
    connection: duckdb.DuckDBPyConnection,
    policy: ModelPromotionConfig,
    assessment: PromotionAssessment,
    metrics: dict[str, Any],
    calibration_method: str | None,
    uncertainty_adjustment: float,
    assessed_at: datetime,
) -> None:
    evaluation_path = str(assessment.evaluation_path) if assessment.evaluation_path else ""
    key = (
        f"{assessment.version}:{assessment.market_family}:{policy.policy_version}:"
        f"{evaluation_path}:{assessed_at.isoformat()}"
    )
    assessment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-engine:promotion:{key}"))
    calibration_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-engine:calibration:{key}"))
    role_name = f"{assessment.market_family}_CHAMPION"
    role_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-engine:role:{assessment.version}:{role_name}"))
    calibration_gate = _mapping(assessment.gate_results["calibration"])
    evaluation_window = {
        "evaluation_path": evaluation_path or None,
        "policy_version": policy.policy_version,
    }
    connection.begin()
    try:
        connection.execute(
            "INSERT INTO model_promotion_assessments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (assessment_id) DO NOTHING",
            [
                assessment_id,
                assessment.version,
                assessment.model_type,
                assessment.market_family,
                policy.policy_version,
                assessment.state,
                _json(assessment.reasons),
                _json(assessment.gate_results),
                evaluation_path,
                assessed_at,
            ],
        )
        connection.execute(
            "INSERT INTO calibration_validations VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (validation_id) DO UPDATE SET state=excluded.state, metrics=excluded.metrics, "
            "validated_at=excluded.validated_at",
            [
                calibration_id,
                assessment.version,
                assessment.market_family,
                "CALIBRATION_VALIDATED" if calibration_gate.get("passed") else "CALIBRATION_FAILED",
                calibration_method or "none",
                _json(evaluation_window),
                _json(calibration_gate),
                assessed_at,
            ],
        )
        if assessment.state == "PROMOTED":
            prior = connection.execute(
                "SELECT model_version, model_type FROM model_market_roles WHERE market_family=? AND role_name=? "
                "AND state='CHAMPION' AND model_version<>? ORDER BY selected_at DESC LIMIT 1",
                [assessment.market_family, role_name, assessment.version],
            ).fetchone()
            connection.execute(
                "UPDATE model_market_roles SET state='RESEARCH_ONLY', selected_at=? "
                "WHERE market_family=? AND role_name=? AND state='CHAMPION' AND model_version<>?",
                [assessed_at, assessment.market_family, role_name, assessment.version],
            )
            if prior:
                _persist_role_event(
                    connection,
                    market_family=assessment.market_family,
                    role_name=role_name,
                    model_version=str(prior[0]),
                    model_type=str(prior[1]),
                    state="RESEARCH_ONLY",
                    event_type="SUPERSEDED",
                    assessment_id=assessment_id,
                    occurred_at=assessed_at,
                    evidence={"superseded_by": assessment.version},
                )
                _revoke_pending_production_opportunities(
                    connection,
                    model_version=str(prior[0]),
                    assessed_at=assessed_at,
                    reason="MODEL_ROLE_SUPERSEDED",
                )
            metrics = {
                **metrics,
                "uncertainty_policy": {
                    "validated": True,
                    "policy_version": policy.policy_version,
                    "market_family": assessment.market_family,
                    "expected_return_adjustment": uncertainty_adjustment,
                    "assessment_id": assessment_id,
                },
                "minimum_odds_policy": {
                    "validated": True,
                    "policy_version": policy.policy_version,
                    "market_family": assessment.market_family,
                    "required_expected_return": policy.base_required_expected_return,
                    "assessment_id": assessment_id,
                },
            }
            connection.execute(
                "UPDATE model_runs SET status='champion', metrics=? WHERE version=? AND status='candidate'",
                [_json(metrics), assessment.version],
            )
            if prior:
                connection.execute(
                    "UPDATE model_runs SET status='retired' WHERE version=? AND NOT EXISTS ("
                    "SELECT 1 FROM model_market_roles WHERE model_version=? AND state='CHAMPION')",
                    [prior[0], prior[0]],
                )
            role_state = "CHAMPION"
        else:
            # Incumbents are reassessed on every cycle. If newer evidence or a
            # stricter policy invalidates an incumbent, fail closed immediately
            # rather than leaving a stale champion available to prediction code.
            connection.execute(
                "UPDATE model_market_roles SET state='RESEARCH_ONLY', selected_at=? "
                "WHERE market_family=? AND role_name=? AND model_version=? AND state='CHAMPION'",
                [assessed_at, assessment.market_family, role_name, assessment.version],
            )
            connection.execute(
                "UPDATE model_runs SET status='candidate' WHERE version=? AND status='champion'",
                [assessment.version],
            )
            _revoke_pending_production_opportunities(
                connection,
                model_version=assessment.version,
                assessed_at=assessed_at,
                reason="MODEL_ROLE_REVOKED",
            )
            role_state = "CHALLENGER"
        connection.execute(
            "INSERT INTO model_market_roles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (role_id) DO UPDATE SET state=excluded.state, evaluation_window=excluded.evaluation_window, "
            "metrics=excluded.metrics, uncertainty=excluded.uncertainty, market_baseline=excluded.market_baseline, "
            "selected_at=excluded.selected_at",
            [
                role_id,
                assessment.market_family,
                role_name,
                assessment.version,
                assessment.model_type,
                role_state,
                _json(evaluation_window),
                _json(metrics),
                _json(assessment.gate_results["uncertainty"]),
                _json(assessment.gate_results["market_baseline"]),
                assessed_at,
            ],
        )
        _persist_role_event(
            connection,
            market_family=assessment.market_family,
            role_name=role_name,
            model_version=assessment.version,
            model_type=assessment.model_type,
            state=role_state,
            event_type="PROMOTED" if assessment.state == "PROMOTED" else "WITHHELD",
            assessment_id=assessment_id,
            occurred_at=assessed_at,
            evidence={"policy_version": policy.policy_version, "reasons": assessment.reasons},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _persist_role_event(
    connection: duckdb.DuckDBPyConnection,
    *,
    market_family: str,
    role_name: str,
    model_version: str,
    model_type: str,
    state: str,
    event_type: str,
    assessment_id: str,
    occurred_at: datetime,
    evidence: dict[str, Any],
) -> None:
    event_key = f"{model_version}:{role_name}:{event_type}:{assessment_id}:{occurred_at.isoformat()}"
    connection.execute(
        "INSERT INTO model_market_role_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (event_id) DO NOTHING",
        [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-engine:role-event:{event_key}")),
            market_family,
            role_name,
            model_version,
            model_type,
            state,
            event_type,
            assessment_id,
            occurred_at,
            _json(evidence),
        ],
    )


def _revoke_pending_production_opportunities(
    connection: duckdb.DuckDBPyConnection,
    *,
    model_version: str,
    assessed_at: datetime,
    reason: str,
) -> None:
    rows = connection.execute(
        "SELECT CAST(o.opportunity_id AS VARCHAR), o.reason_codes "
        "FROM institutional_opportunities o "
        "JOIN institutional_predictions p USING (prediction_id) "
        "JOIN fixtures f ON f.fixture_id=p.target_fixture_id "
        "WHERE p.fundamental_model_version=? "
        "AND o.governance_state='PRODUCTION_ACTIONABLE' AND f.kickoff_utc>?",
        [model_version, assessed_at],
    ).fetchall()
    for opportunity_id, raw_reasons in rows:
        parsed = json.loads(raw_reasons) if isinstance(raw_reasons, str) else raw_reasons
        reasons = list(parsed) if isinstance(parsed, list) else []
        reasons.append(reason)
        connection.execute(
            "UPDATE institutional_opportunities SET governance_state='RESEARCH_VALUE_SIGNAL', "
            "decision='NO_BET', reason_codes=? WHERE opportunity_id=?",
            [_json(list(dict.fromkeys(reasons))), opportunity_id],
        )


def _latest_report(
    evaluation_dir: Path,
    model_type: str,
    dataset_hash: str,
    candidate_version: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    reports: list[tuple[str, Path, dict[str, Any]]] = []
    # Recursive discovery supports date-partitioned reports while retaining
    # compatibility with evaluation files written directly under this root.
    for path in evaluation_dir.rglob(f"{model_type}-{dataset_hash[:12]}-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            payload.get("model_type") == model_type
            and payload.get("dataset_hash") == dataset_hash
            and payload.get("candidate_version") == candidate_version
        ):
            reports.append((str(payload.get("created_at", "")), path, payload))
    if not reports:
        return None, None
    _, path, payload = max(reports, key=lambda item: item[0])
    return path, payload


def _incumbent(
    connection: duckdb.DuckDBPyConnection, market_family: str, candidate_version: str
) -> tuple[str | None, dict[str, Any]]:
    row = connection.execute(
        "SELECT mr.version, mr.metrics FROM model_market_roles r JOIN model_runs mr "
        "ON mr.version=r.model_version WHERE r.market_family=? AND r.role_name=? AND r.state='CHAMPION' "
        "AND mr.version<>? ORDER BY r.selected_at DESC LIMIT 1",
        [market_family, f"{market_family}_CHAMPION", candidate_version],
    ).fetchone()
    return (str(row[0]), _mapping(row[1])) if row else (None, {})


def _uncertainty_adjustment(
    policy: ModelPromotionConfig, calibrated_ece: float | None, log_interval: dict[str, Any]
) -> float:
    estimate = _number(log_interval.get("estimate"))
    upper = _number(log_interval.get("upper"))
    interval_width = max(0.0, upper - estimate) if estimate is not None and upper is not None else 1.0
    calibration_width = calibrated_ece if calibrated_ece is not None else 1.0
    return max(policy.minimum_uncertainty_adjustment, calibration_width, interval_width)


def _better(candidate: dict[str, Any], comparator: dict[str, Any]) -> bool:
    candidate_log = _number(candidate.get("log_loss"))
    candidate_brier = _number(candidate.get("brier"))
    comparator_log = _number(comparator.get("log_loss"))
    comparator_brier = _number(comparator.get("brier"))
    return bool(
        candidate_log is not None
        and candidate_brier is not None
        and comparator_log is not None
        and comparator_brier is not None
        and candidate_log < comparator_log
        and candidate_brier <= comparator_brier
    )


def _not_worse(candidate: dict[str, Any], comparator: dict[str, Any]) -> bool:
    candidate_log = _number(candidate.get("log_loss"))
    candidate_brier = _number(candidate.get("brier"))
    comparator_log = _number(comparator.get("log_loss"))
    comparator_brier = _number(comparator.get("brier"))
    tolerance = 1e-12
    return bool(
        candidate_log is not None
        and candidate_brier is not None
        and comparator_log is not None
        and comparator_brier is not None
        and candidate_log <= comparator_log + tolerance
        and candidate_brier <= comparator_brier + tolerance
    )


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)
