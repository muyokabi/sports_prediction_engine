from dataclasses import dataclass

import numpy as np

from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.markets.settlement import SettlementDistribution, asian_handicap, asian_total


@dataclass(frozen=True, slots=True)
class CoreMarketPrices:
    distribution: ScoreDistribution
    home: float
    draw: float
    away: float
    btts_yes: float
    btts_no: float

    @classmethod
    def from_distribution(cls, distribution: ScoreDistribution) -> "CoreMarketPrices":
        matrix = distribution.probabilities
        if matrix.ndim != 2 or matrix.size == 0:
            raise ValueError("Score distribution must be a non-empty two-dimensional matrix")
        if not np.isclose(float(matrix.sum()), 1.0, atol=1e-8):
            raise ValueError("Score distribution probabilities must sum to one")
        home_goals, away_goals = np.indices(matrix.shape)
        return cls(
            distribution,
            float(matrix[home_goals > away_goals].sum()),
            float(matrix[home_goals == away_goals].sum()),
            float(matrix[home_goals < away_goals].sum()),
            float(matrix[(home_goals > 0) & (away_goals > 0)].sum()),
            float(matrix[(home_goals == 0) | (away_goals == 0)].sum()),
        )

    @classmethod
    def from_expected_goals(
        cls,
        home_expected_goals: float,
        away_expected_goals: float,
        *,
        tail_tolerance: float = 1e-10,
    ) -> "CoreMarketPrices":
        distribution = ScoreDistribution.poisson(
            home_expected_goals,
            away_expected_goals,
            tail_tolerance=tail_tolerance,
        )
        return cls.from_distribution(distribution)

    def double_chance(self) -> dict[str, float]:
        return {"1X": self.home + self.draw, "12": self.home + self.away, "X2": self.draw + self.away}

    def draw_no_bet(self, side: str) -> SettlementDistribution:
        return asian_handicap(self.distribution, 0.0, side=side)

    def asian_handicap(self, line: float, side: str) -> SettlementDistribution:
        return asian_handicap(self.distribution, line, side=side)

    def total(self, line: float, side: str) -> SettlementDistribution:
        return asian_total(self.distribution, line, side=side)

    def team_total(self, line: float, *, team: str, side: str) -> SettlementDistribution:
        if team not in {"home", "away"}:
            raise ValueError("Team must be 'home' or 'away'")
        matrix = self.distribution.probabilities
        home_goals, away_goals = np.indices(matrix.shape)
        goals = home_goals if team == "home" else away_goals
        margin = goals.astype(float) if side == "over" else -goals.astype(float)
        adjusted_line = line if side == "over" else -line
        from sports_engine.markets.settlement import _settle_margin

        return _settle_margin(matrix, margin, -adjusted_line)

    def correct_score(self, home_goals: int, away_goals: int) -> float:
        if home_goals < 0 or away_goals < 0:
            raise ValueError("Goals cannot be negative")
        matrix = self.distribution.probabilities
        if home_goals >= matrix.shape[0] or away_goals >= matrix.shape[1]:
            return 0.0
        return float(matrix[home_goals, away_goals])
