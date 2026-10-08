from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class NoBetReason(StrEnum):
    INSUFFICIENT_HISTORICAL_SAMPLE = "INSUFFICIENT_HISTORICAL_SAMPLE"
    INSUFFICIENT_CLASS_OBSERVATIONS = "INSUFFICIENT_CLASS_OBSERVATIONS"
    INSUFFICIENT_VALIDATION_SAMPLE = "INSUFFICIENT_VALIDATION_SAMPLE"
    INSUFFICIENT_TEST_SAMPLE = "INSUFFICIENT_TEST_SAMPLE"
    INSUFFICIENT_TEAM_HISTORY = "INSUFFICIENT_TEAM_HISTORY"
    INCOMPLETE_MATCH_HISTORY = "INCOMPLETE_MATCH_HISTORY"
    MODEL_NOT_SUFFICIENTLY_VALIDATED = "MODEL_NOT_SUFFICIENTLY_VALIDATED"
    MODEL_NOT_CALIBRATED = "MODEL_NOT_CALIBRATED"
    NO_CHAMPION_MODEL = "NO_CHAMPION_MODEL"
    MISSING_ODDS = "MISSING_ODDS"
    INVALID_REFERENCE_ODDS = "INVALID_REFERENCE_ODDS"
    POST_KICKOFF_REFERENCE = "POST_KICKOFF_REFERENCE"
    FIXTURE_ALREADY_STARTED = "FIXTURE_ALREADY_STARTED"
    INCOMPLETE_FIXTURE_DATA = "INCOMPLETE_FIXTURE_DATA"
    MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
    INSUFFICIENT_PROBABILITY_ADVANTAGE = "INSUFFICIENT_PROBABILITY_ADVANTAGE"
    NON_POSITIVE_EXPECTED_VALUE = "NON_POSITIVE_EXPECTED_VALUE"
    EXCESSIVE_UNCERTAINTY = "EXCESSIVE_UNCERTAINTY"
    DAILY_EXPOSURE_LIMIT = "DAILY_EXPOSURE_LIMIT"
    SIMULTANEOUS_RECOMMENDATION_LIMIT = "SIMULTANEOUS_RECOMMENDATION_LIMIT"


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    minimum_training_fixtures: int
    minimum_class_observations: int
    minimum_validation_fixtures: int
    minimum_test_fixtures: int
    minimum_team_history: int
    require_calibration: bool
    minimum_prediction_confidence: float


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    maximum_bankroll_fraction_per_wager: float
    maximum_daily_exposure: float
    maximum_simultaneous_recommendations: int
    fractional_kelly: float
    hard_stake_cap: float
    minimum_probability_advantage: float
    minimum_expected_value: float


@dataclass(frozen=True, slots=True)
class MarketQuote:
    outcome: str
    fair_probability: float
    decimal_odds: float
    observed_at: datetime
    bookmaker: str | None = None
    provider_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BettingDecision:
    state: str
    reasons: tuple[str, ...]
    selected_market: str | None = None
    model_probability: float | None = None
    market_fair_probability: float | None = None
    reference_decimal_odds: float | None = None
    raw_implied_probability: float | None = None
    reference_expected_value: float | None = None
    minimum_acceptable_odds: float | None = None
    odds_observed_at: datetime | None = None
    stake_fraction: float | None = None
    reference_state: str | None = None
    execution_edge: float | None = None
    manual_price_confirmation_required: bool = True


def decide_wager(
    probabilities: dict[str, float],
    quotes: list[MarketQuote],
    *,
    decision_time: datetime,
    fixture_kickoff: datetime | None = None,
    model_metrics: dict[str, object],
    calibrated: bool,
    home_history: int,
    away_history: int,
    evidence: EvidencePolicy,
    risk: RiskPolicy,
    current_daily_exposure: float = 0.0,
    active_recommendations: int = 0,
) -> BettingDecision:
    def count(name: str) -> int:
        value = model_metrics.get(name, 0)
        return int(value) if isinstance(value, (int, float, str)) else 0

    reasons: list[str] = []
    if fixture_kickoff is not None and decision_time >= fixture_kickoff:
        return BettingDecision(
            "NO_BET",
            (NoBetReason.FIXTURE_ALREADY_STARTED,),
            manual_price_confirmation_required=True,
        )
    evidence_state = model_metrics.get("evidence_state")
    if evidence_state is not None:
        if str(evidence_state) != "PRODUCTION_ACTIONABLE":
            reasons.append(NoBetReason.MODEL_NOT_SUFFICIENTLY_VALIDATED)
    elif count("train_rows") < evidence.minimum_training_fixtures:
        reasons.append(NoBetReason.INSUFFICIENT_HISTORICAL_SAMPLE)
    class_counts = model_metrics.get("training_class_counts", {})
    observed_classes = (
        [int(value) for value in class_counts.values() if isinstance(value, (int, float, str))]
        if isinstance(class_counts, dict)
        else []
    )
    if evidence_state is None and min(observed_classes, default=0) < evidence.minimum_class_observations:
        reasons.append(NoBetReason.INSUFFICIENT_CLASS_OBSERVATIONS)
    if evidence_state is None and count("validation_rows") < evidence.minimum_validation_fixtures:
        reasons.append(NoBetReason.INSUFFICIENT_VALIDATION_SAMPLE)
    if evidence_state is None and count("test_rows") < evidence.minimum_test_fixtures:
        reasons.append(NoBetReason.INSUFFICIENT_TEST_SAMPLE)
    if min(home_history, away_history) < evidence.minimum_team_history:
        reasons.append(NoBetReason.INSUFFICIENT_TEAM_HISTORY)
    calibration_required = bool(model_metrics.get("calibration_required", evidence.require_calibration))
    if calibration_required and not calibrated:
        reasons.append(NoBetReason.MODEL_NOT_CALIBRATED)
    if max(probabilities.values()) < evidence.minimum_prediction_confidence:
        reasons.append(NoBetReason.EXCESSIVE_UNCERTAINTY)
    valid_quotes = [quote for quote in quotes if quote.decimal_odds > 1 and quote.observed_at <= decision_time]
    if fixture_kickoff is not None:
        post_kickoff = [quote for quote in valid_quotes if quote.observed_at >= fixture_kickoff]
        valid_quotes = [quote for quote in valid_quotes if quote.observed_at < fixture_kickoff]
        if post_kickoff and not valid_quotes:
            reasons.append(NoBetReason.POST_KICKOFF_REFERENCE)
    if len(valid_quotes) < len(quotes) and not valid_quotes:
        reasons.append(NoBetReason.INVALID_REFERENCE_ODDS)
    if not valid_quotes:
        reasons.append(NoBetReason.MISSING_ODDS)
        non_market_reasons = [reason for reason in reasons if reason != NoBetReason.MISSING_ODDS]
        return BettingDecision(
            "NO_BET" if non_market_reasons else "PRICE_TARGET",
            tuple(dict.fromkeys(reasons)),
            manual_price_confirmation_required=True,
        )
    candidates = []
    for quote in valid_quotes:
        probability = probabilities[quote.outcome]
        advantage = probability - quote.fair_probability
        expected_value = probability * quote.decimal_odds - 1
        if advantage >= risk.minimum_probability_advantage and expected_value >= risk.minimum_expected_value:
            candidates.append((expected_value, quote, probability))
    if not candidates:
        if all(
            probabilities[q.outcome] - q.fair_probability < risk.minimum_probability_advantage for q in valid_quotes
        ):
            reasons.append(NoBetReason.INSUFFICIENT_PROBABILITY_ADVANTAGE)
        if all(probabilities[q.outcome] * q.decimal_odds - 1 < risk.minimum_expected_value for q in valid_quotes):
            reasons.append(NoBetReason.NON_POSITIVE_EXPECTED_VALUE)
    if current_daily_exposure >= risk.maximum_daily_exposure:
        reasons.append(NoBetReason.DAILY_EXPOSURE_LIMIT)
    if active_recommendations >= risk.maximum_simultaneous_recommendations:
        reasons.append(NoBetReason.SIMULTANEOUS_RECOMMENDATION_LIMIT)
    if reasons or not candidates:
        return BettingDecision("NO_BET", tuple(dict.fromkeys(reasons)))
    expected_value, quote, probability = max(candidates, key=lambda value: value[0])
    denominator = quote.decimal_odds - 1
    kelly = max(0.0, (probability * quote.decimal_odds - 1) / denominator) if denominator > 0 else 0.0
    stake = min(
        kelly * risk.fractional_kelly,
        risk.hard_stake_cap,
        risk.maximum_bankroll_fraction_per_wager,
        max(0.0, risk.maximum_daily_exposure - current_daily_exposure),
    )
    if not 0 < stake <= 1:
        return BettingDecision("NO_BET", (NoBetReason.NON_POSITIVE_EXPECTED_VALUE,))
    return BettingDecision(
        "BET_IF_PRICE_AVAILABLE",
        (),
        quote.outcome,
        probability,
        quote.fair_probability,
        quote.decimal_odds,
        1 / quote.decimal_odds,
        expected_value,
        (1 + risk.minimum_expected_value) / probability,
        quote.observed_at,
        stake,
        "LATEST_PROVIDER_REFERENCE",
        None,
        True,
    )
