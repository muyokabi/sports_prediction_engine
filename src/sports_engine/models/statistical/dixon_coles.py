from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize_scalar

from sports_engine.models.statistical.poisson import PoissonModel


@dataclass
class DixonColesModel(PoissonModel):
    rho: float = -0.1

    def fit(self, matches: list[tuple[str, str, int, int]]) -> "DixonColesModel":
        super().fit(matches)
        return self._fit_rho(matches)

    def fit_timed(
        self,
        matches: list[tuple[str, str, int, int, datetime]],
        *,
        half_life_days: float,
        reference_time: datetime | None = None,
    ) -> "DixonColesModel":
        super().fit_timed(matches, half_life_days=half_life_days, reference_time=reference_time)
        return self._fit_rho([(home, away, hg, ag) for home, away, hg, ag, _ in matches])

    def _fit_rho(self, matches: list[tuple[str, str, int, int]]) -> "DixonColesModel":
        rates = [self.expected_goals(home, away) for home, away, _, _ in matches]
        maximum_rate = max(max(home_rate, away_rate) for home_rate, away_rate in rates)
        maximum_product = max(home_rate * away_rate for home_rate, away_rate in rates)
        lower = max(-0.25, -0.999 / max(maximum_rate, 1e-12))
        upper = min(0.25, 0.999 / max(maximum_product, 1e-12), 0.999)
        if lower >= upper:
            raise RuntimeError("No valid Dixon-Coles rho interval preserves positive probability mass")

        def objective(rho: float) -> float:
            loss = 0.0
            for home, away, home_goals, away_goals in matches:
                home_rate, away_rate = self.expected_goals(home, away)
                adjustment = self._tau(home_goals, away_goals, home_rate, away_rate, rho)
                loss -= np.log(max(adjustment, 1e-12))
            return float(loss)

        fitted = minimize_scalar(objective, bounds=(lower, upper), method="bounded")
        if not fitted.success:
            raise RuntimeError("Dixon-Coles rho optimization failed")
        self.rho = float(fitted.x)
        return self

    def score_matrix(self, home: str, away: str) -> np.ndarray:
        matrix = super().score_matrix(home, away)
        home_rate, away_rate = self.expected_goals(home, away)
        for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1)):
            matrix[home_goals, away_goals] *= self._tau(home_goals, away_goals, home_rate, away_rate, self.rho)
        matrix = np.clip(matrix, 0.0, None)
        return matrix / matrix.sum()

    @staticmethod
    def _tau(
        home_goals: int,
        away_goals: int,
        home_rate: float,
        away_rate: float,
        rho: float,
    ) -> float:
        if (home_goals, away_goals) == (0, 0):
            return 1 - home_rate * away_rate * rho
        if (home_goals, away_goals) == (0, 1):
            return 1 + home_rate * rho
        if (home_goals, away_goals) == (1, 0):
            return 1 + away_rate * rho
        if (home_goals, away_goals) == (1, 1):
            return 1 - rho
        return 1.0

    def metadata(self) -> dict[str, object]:
        return {"model_type": "dixon_coles", "maximum_goals": self.maximum_goals, "rho": self.rho}
