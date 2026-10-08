from datetime import UTC, datetime, timedelta

import pytest

from sports_engine.markets.decision import (
    EvidencePolicy,
    MarketQuote,
    NoBetReason,
    RiskPolicy,
    decide_wager,
)

EVIDENCE = EvidencePolicy(100, 20, 30, 30, 10, True, 0.4)
RISK = RiskPolicy(0.01, 0.05, 5, 0.25, 0.01, 0.03, 0.0)
METRICS = {
    "train_rows": 300,
    "validation_rows": 60,
    "test_rows": 60,
    "training_class_counts": {"HOME": 100, "DRAW": 100, "AWAY": 100},
}


def test_aged_reference_remains_usable_and_requires_manual_price_check() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    decision = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        [MarketQuote("home", 0.45, 2.2, now - timedelta(hours=4))],
        decision_time=now,
        model_metrics=METRICS,
        calibrated=True,
        home_history=20,
        away_history=20,
        evidence=EVIDENCE,
        risk=RISK,
    )
    assert decision.state == "BET_IF_PRICE_AVAILABLE"
    assert decision.reference_decimal_odds == pytest.approx(2.2)
    assert decision.execution_edge is None
    assert decision.manual_price_confirmation_required


def test_evidence_gates_abstain_and_valid_quote_has_bounded_stake() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    quote = [MarketQuote("home", 0.45, 2.2, now - timedelta(minutes=5))]
    blocked = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        quote,
        decision_time=now,
        model_metrics={},
        calibrated=False,
        home_history=1,
        away_history=1,
        evidence=EVIDENCE,
        risk=RISK,
    )
    assert blocked.state == "NO_BET"
    assert NoBetReason.MODEL_NOT_CALIBRATED in blocked.reasons
    allowed = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        quote,
        decision_time=now,
        model_metrics=METRICS,
        calibrated=True,
        home_history=20,
        away_history=20,
        evidence=EVIDENCE,
        risk=RISK,
    )
    assert allowed.state == "BET_IF_PRICE_AVAILABLE"
    assert allowed.reference_expected_value == pytest.approx(0.32)
    assert allowed.minimum_acceptable_odds == pytest.approx(1 / 0.6)
    assert allowed.stake_fraction == pytest.approx(0.01)


def test_model_specific_evidence_state_replaces_global_row_thresholds() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    policy_with_impossible_legacy_thresholds = EvidencePolicy(10_000, 1_000, 1_000, 1_000, 1, True, 0.3)
    metrics = {
        "evidence_state": "PRODUCTION_ACTIONABLE",
        "calibration_required": False,
        "train_rows": 40,
    }
    decision = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        [MarketQuote("home", 0.45, 2.2, now)],
        decision_time=now,
        model_metrics=metrics,
        calibrated=False,
        home_history=20,
        away_history=20,
        evidence=policy_with_impossible_legacy_thresholds,
        risk=RISK,
    )
    assert decision.state == "BET_IF_PRICE_AVAILABLE"


def test_non_actionable_model_specific_state_forces_abstention() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    decision = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        [MarketQuote("home", 0.45, 2.2, now)],
        decision_time=now,
        model_metrics={"evidence_state": "RESEARCH_TRAINABLE", "calibration_required": False},
        calibrated=False,
        home_history=20,
        away_history=20,
        evidence=EvidencePolicy(0, 0, 0, 0, 1, False, 0.3),
        risk=RISK,
    )
    assert decision.state == "NO_BET"
    assert NoBetReason.MODEL_NOT_SUFFICIENTLY_VALIDATED in decision.reasons


def test_started_fixture_is_blocked_even_with_valid_prematch_reference() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    decision = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        [MarketQuote("home", 0.45, 2.2, now - timedelta(hours=2))],
        decision_time=now,
        fixture_kickoff=now - timedelta(minutes=1),
        model_metrics=METRICS,
        calibrated=True,
        home_history=20,
        away_history=20,
        evidence=EVIDENCE,
        risk=RISK,
    )
    assert decision.state == "NO_BET"
    assert decision.reasons == (NoBetReason.FIXTURE_ALREADY_STARTED,)
