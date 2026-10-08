from dataclasses import dataclass
from enum import StrEnum
from math import isclose

import numpy as np

from sports_engine.markets.score_distribution import ScoreDistribution


class Settlement(StrEnum):
    FULL_WIN = "FULL_WIN"
    HALF_WIN = "HALF_WIN"
    PUSH = "PUSH"
    HALF_LOSS = "HALF_LOSS"
    FULL_LOSS = "FULL_LOSS"


@dataclass(frozen=True, slots=True)
class SettlementDistribution:
    full_win: float = 0.0
    half_win: float = 0.0
    push: float = 0.0
    half_loss: float = 0.0
    full_loss: float = 0.0

    def __post_init__(self) -> None:
        values = self.as_dict().values()
        if any(value < -1e-12 for value in values):
            raise ValueError("Settlement probabilities cannot be negative")
        if not isclose(sum(values), 1.0, abs_tol=1e-9):
            raise ValueError("Settlement probabilities must sum to one")

    def as_dict(self) -> dict[Settlement, float]:
        return {
            Settlement.FULL_WIN: self.full_win,
            Settlement.HALF_WIN: self.half_win,
            Settlement.PUSH: self.push,
            Settlement.HALF_LOSS: self.half_loss,
            Settlement.FULL_LOSS: self.full_loss,
        }

    @property
    def win_exposure(self) -> float:
        return self.full_win + self.half_win / 2

    @property
    def loss_exposure(self) -> float:
        return self.full_loss + self.half_loss / 2

    def expected_return(self, decimal_odds: float) -> float:
        if decimal_odds <= 1:
            raise ValueError("Decimal odds must be greater than one")
        return self.win_exposure * (decimal_odds - 1) - self.loss_exposure

    def fair_odds(self) -> float | None:
        return self.minimum_odds(0.0)

    def minimum_odds(self, minimum_expected_return: float) -> float | None:
        if minimum_expected_return < 0:
            raise ValueError("Minimum expected return cannot be negative")
        if self.win_exposure <= 0:
            return None
        return 1 + (self.loss_exposure + minimum_expected_return) / self.win_exposure


@dataclass(frozen=True, slots=True)
class ManualPriceCheck:
    passes: bool
    actual_decimal_odds: float
    minimum_acceptable_odds: float
    expected_return: float


def check_manual_price(
    distribution: SettlementDistribution,
    actual_decimal_odds: float,
    *,
    required_expected_return: float,
) -> ManualPriceCheck:
    minimum = distribution.minimum_odds(required_expected_return)
    if minimum is None:
        raise ValueError("A price target is undefined when there is no win exposure")
    expected_return = distribution.expected_return(actual_decimal_odds)
    return ManualPriceCheck(
        actual_decimal_odds + 1e-12 >= minimum,
        actual_decimal_odds,
        minimum,
        expected_return,
    )


def asian_handicap(
    distribution: ScoreDistribution,
    line: float,
    *,
    side: str,
) -> SettlementDistribution:
    if side not in {"home", "away"}:
        raise ValueError("Asian handicap side must be 'home' or 'away'")
    home_goals, away_goals = np.indices(distribution.probabilities.shape)
    margin = home_goals - away_goals if side == "home" else away_goals - home_goals
    return _settle_margin(distribution.probabilities, margin.astype(float), line)


def asian_total(
    distribution: ScoreDistribution,
    line: float,
    *,
    side: str,
) -> SettlementDistribution:
    if side not in {"over", "under"}:
        raise ValueError("Asian total side must be 'over' or 'under'")
    home_goals, away_goals = np.indices(distribution.probabilities.shape)
    total = (home_goals + away_goals).astype(float)
    margin = total if side == "over" else -total
    adjusted_line = -line if side == "under" else line
    return _settle_margin(distribution.probabilities, margin, -adjusted_line)


def _settle_margin(probabilities: np.ndarray, margin: np.ndarray, line: float) -> SettlementDistribution:
    scaled = line * 4
    if not isclose(scaled, round(scaled), abs_tol=1e-9):
        raise ValueError("Only whole, half, and quarter lines are supported")
    quarter = int(round(scaled))
    if quarter % 2 == 0:
        return _single_line(probabilities, margin + line)
    lower = (quarter - 1) / 4
    upper = (quarter + 1) / 4
    left = _single_outcomes(margin + lower)
    right = _single_outcomes(margin + upper)
    buckets = {settlement: 0.0 for settlement in Settlement}
    for first in (-1, 0, 1):
        for second in (-1, 0, 1):
            mask = (left == first) & (right == second)
            buckets[_combined_settlement(first, second)] += float(probabilities[mask].sum())
    return _from_buckets(buckets)


def _single_line(probabilities: np.ndarray, adjusted_margin: np.ndarray) -> SettlementDistribution:
    outcomes = _single_outcomes(adjusted_margin)
    return SettlementDistribution(
        full_win=float(probabilities[outcomes == 1].sum()),
        push=float(probabilities[outcomes == 0].sum()),
        full_loss=float(probabilities[outcomes == -1].sum()),
    )


def _single_outcomes(adjusted_margin: np.ndarray) -> np.ndarray:
    return np.where(adjusted_margin > 1e-12, 1, np.where(adjusted_margin < -1e-12, -1, 0))


def _combined_settlement(left: int, right: int) -> Settlement:
    score = left + right
    return {
        2: Settlement.FULL_WIN,
        1: Settlement.HALF_WIN,
        0: Settlement.PUSH if left == right == 0 else Settlement.HALF_WIN if min(left, right) == 0 else Settlement.PUSH,
        -1: Settlement.HALF_LOSS,
        -2: Settlement.FULL_LOSS,
    }[score]


def _from_buckets(values: dict[Settlement, float]) -> SettlementDistribution:
    return SettlementDistribution(
        values[Settlement.FULL_WIN],
        values[Settlement.HALF_WIN],
        values[Settlement.PUSH],
        values[Settlement.HALF_LOSS],
        values[Settlement.FULL_LOSS],
    )
