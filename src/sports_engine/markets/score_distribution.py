from dataclasses import dataclass
from math import exp

import numpy as np


@dataclass(frozen=True, slots=True)
class ScoreDistribution:
    """A normalized independent-Poisson score grid with an explicit tail bound."""

    home_expected_goals: float
    away_expected_goals: float
    probabilities: np.ndarray
    omitted_probability: float

    @classmethod
    def poisson(
        cls,
        home_expected_goals: float,
        away_expected_goals: float,
        *,
        tail_tolerance: float = 1e-10,
    ) -> "ScoreDistribution":
        if home_expected_goals < 0 or away_expected_goals < 0:
            raise ValueError("Expected goals cannot be negative")
        if not 0 < tail_tolerance < 1:
            raise ValueError("tail_tolerance must be between zero and one")
        home = _poisson_mass(home_expected_goals, tail_tolerance / 2)
        away = _poisson_mass(away_expected_goals, tail_tolerance / 2)
        matrix = np.outer(home, away)
        represented = float(matrix.sum())
        if represented <= 0:
            raise ValueError("Score distribution has no probability mass")
        return cls(home_expected_goals, away_expected_goals, matrix / represented, 1.0 - represented)

    @property
    def expected_total(self) -> float:
        return self.home_expected_goals + self.away_expected_goals

    @property
    def expected_supremacy(self) -> float:
        return self.home_expected_goals - self.away_expected_goals


def _poisson_mass(rate: float, tail_tolerance: float) -> np.ndarray:
    if rate == 0:
        return np.asarray([1.0])
    values = [exp(-rate)]
    cumulative = values[0]
    goals = 0
    while 1.0 - cumulative > tail_tolerance:
        goals += 1
        values.append(values[-1] * rate / goals)
        cumulative += values[-1]
        if goals > 10_000:  # mathematical safety guard, not a pricing truncation
            raise RuntimeError("Poisson tail failed to converge")
    return np.asarray(values, dtype=float)
