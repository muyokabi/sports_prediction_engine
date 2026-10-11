from datetime import UTC, datetime, timedelta
from inspect import Parameter, signature

import pytest

from sports_engine.markets.decision import (
    EvidencePolicy,
    MarketQuote,
    NoBetReason,
    RiskPolicy,
    decide_wager,
    validated_nonnegative_policy_value,
)
from sports_engine.sports.football.prediction.service import PredictionService
from sports_engine.training.feedback import _realized_shadow_return


def test_shadow_settlement_handles_binary_and_quarter_total_returns() -> None:
    assert _realized_shadow_return("MATCH_ODDS", "HOME", "", 2.5, 2, 1) == (1.5, "HOME")
    btts_return, btts_outcome = _realized_shadow_return("BTTS", "NO", "", 1.8, 0, 0)
    assert btts_return == pytest.approx(0.8)
    assert btts_outcome == "NO"
    assert _realized_shadow_return("TOTAL_GOALS", "OVER", "2.25", 2.0, 2, 0) == (-0.5, "PUSH/LOSS")
    assert _realized_shadow_return("TOTAL_GOALS", "UNDER", "2.25", 2.0, 2, 0) == (0.5, "PUSH/WIN")


EVIDENCE = EvidencePolicy(100, 20, 30, 30, 10, True, 0.4)
RISK = RiskPolicy(0.01, 0.05, 5, 0.25, 0.01, 0.03, 0.0)
METRICS = {
    "train_rows": 300,
    "validation_rows": 60,
    "test_rows": 60,
    "training_class_counts": {"HOME": 100, "DRAW": 100, "AWAY": 100},
}

GOVERNANCE_GATES = {
    "fixture_applicable": True,
    "competition_actionable": True,
    "market_family_qualified": True,
    "uncertainty_validated": True,
    "margin_threshold_validated": True,
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
        **GOVERNANCE_GATES,
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
        **GOVERNANCE_GATES,
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
        **GOVERNANCE_GATES,
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
        **GOVERNANCE_GATES,
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
        **GOVERNANCE_GATES,
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
        **GOVERNANCE_GATES,
    )
    assert decision.state == "NO_BET"
    assert decision.reasons == (NoBetReason.FIXTURE_ALREADY_STARTED,)


def test_institutional_governance_gates_fail_closed() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    decision = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        [MarketQuote("home", 0.45, 2.2, now)],
        decision_time=now,
        model_metrics=METRICS,
        calibrated=True,
        home_history=20,
        away_history=20,
        evidence=EVIDENCE,
        risk=RISK,
        fixture_applicable=False,
        competition_actionable=False,
        market_family_qualified=False,
        uncertainty_validated=False,
        margin_threshold_validated=False,
    )
    assert decision.state == "NO_BET"
    assert set(decision.reasons) >= {
        NoBetReason.MODEL_NOT_APPLICABLE_TO_FIXTURE,
        NoBetReason.COMPETITION_NOT_ACTIONABLE,
        NoBetReason.MARKET_FAMILY_NOT_QUALIFIED,
        NoBetReason.UNCERTAINTY_NOT_VALIDATED,
        NoBetReason.MARGIN_THRESHOLD_NOT_VALIDATED,
    }


@pytest.mark.parametrize(
    "probabilities",
    [
        {"home": 0.6, "draw": 0.4},
        {"home": 0.8, "draw": 0.3, "away": -0.1},
        {"home": 0.6, "draw": 0.3, "away": 0.2},
        {"home": float("nan"), "draw": 0.5, "away": 0.5},
    ],
)
def test_invalid_probability_vectors_fail_closed(probabilities: dict[str, float]) -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    decision = decide_wager(
        probabilities,
        [MarketQuote("home", 0.45, 2.2, now)],
        decision_time=now,
        model_metrics=METRICS,
        calibrated=True,
        home_history=20,
        away_history=20,
        evidence=EVIDENCE,
        risk=RISK,
        **GOVERNANCE_GATES,
    )
    assert decision.state == "NO_BET"
    assert decision.reasons == (NoBetReason.INVALID_MODEL_PROBABILITIES,)


@pytest.mark.parametrize(
    "quote",
    [
        MarketQuote("unknown", 0.45, 2.2, datetime(2026, 10, 7, 12, tzinfo=UTC)),
        MarketQuote("home", float("nan"), 2.2, datetime(2026, 10, 7, 12, tzinfo=UTC)),
        MarketQuote("home", 0.45, float("inf"), datetime(2026, 10, 7, 12, tzinfo=UTC)),
    ],
)
def test_invalid_reference_values_are_rejected_without_key_errors(quote: MarketQuote) -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    decision = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        [quote],
        decision_time=now,
        model_metrics=METRICS,
        calibrated=True,
        home_history=20,
        away_history=20,
        evidence=EVIDENCE,
        risk=RISK,
        **GOVERNANCE_GATES,
    )
    assert decision.state == "NO_BET"
    assert NoBetReason.INVALID_REFERENCE_ODDS in decision.reasons


def test_institutional_governance_gates_cannot_be_silently_omitted() -> None:
    parameters = signature(decide_wager).parameters
    for name in GOVERNANCE_GATES:
        assert parameters[name].default is Parameter.empty


def test_validated_margin_and_uncertainty_are_consumed_by_execution_decision() -> None:
    governed, margin_validated, uncertainty_validated = PredictionService._governed_risk_policy(
        {
            "minimum_odds_policy": {"validated": True, "required_expected_return": 0.03},
            "uncertainty_policy": {"validated": True, "expected_return_adjustment": 0.02},
        },
        RISK,
    )
    assert margin_validated and uncertainty_validated
    assert governed.minimum_expected_value == pytest.approx(0.05)

    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    decision = decide_wager(
        {"home": 0.6, "draw": 0.2, "away": 0.2},
        [MarketQuote("home", 0.50, 1.7, now)],
        decision_time=now,
        model_metrics=METRICS,
        calibrated=True,
        home_history=20,
        away_history=20,
        evidence=EVIDENCE,
        risk=governed,
        **GOVERNANCE_GATES,
    )
    assert decision.state == "NO_BET"
    assert NoBetReason.NON_POSITIVE_EXPECTED_VALUE in decision.reasons


@pytest.mark.parametrize("bad_value", [None, True, -0.01, float("nan"), "not-a-number"])
def test_invalid_validated_policy_values_fail_closed(bad_value: object) -> None:
    governed, margin_validated, uncertainty_validated = PredictionService._governed_risk_policy(
        {
            "minimum_odds_policy": {"validated": True, "required_expected_return": bad_value},
            "uncertainty_policy": {"validated": True, "expected_return_adjustment": 0.02},
        },
        RISK,
    )
    assert not margin_validated
    assert uncertainty_validated
    assert governed == RISK
    assert (
        validated_nonnegative_policy_value(
            {"validated": True, "required_expected_return": bad_value},
            "required_expected_return",
        )
        is None
    )
