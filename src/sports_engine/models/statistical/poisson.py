from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Self

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.models.serialization import load_pickle, save_pickle


@dataclass
class PoissonModel:
    """Regularized attack/defence Poisson model with an explicit home effect."""

    maximum_goals: int = 10
    # Sparse, pooled multi-competition data needs strong partial pooling.  A
    # near-zero penalty lets one-appearance teams acquire extreme parameters
    # and destroys chronological generalisation.
    regularization: float = 10.0
    team_attack: dict[str, float] = field(default_factory=dict)
    team_defense: dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0
    home_advantage: float = 0.0
    fitted_teams: tuple[str, ...] = ()
    # Populated by the trainer from the exact chronological training rows.
    # Older artifacts do not carry this lineage and must therefore fail closed
    # when fixture-level competition applicability is assessed.
    fitted_competitions: tuple[str, ...] = ()

    def fit(self, matches: list[tuple[str, str, int, int]]) -> Self:
        return self._fit(matches, np.ones(len(matches), dtype=float))

    def fit_timed(
        self,
        matches: list[tuple[str, str, int, int, datetime]],
        *,
        half_life_days: float,
        reference_time: datetime | None = None,
    ) -> Self:
        if half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        if not matches:
            raise ValueError("At least one completed match is required")
        reference = reference_time or max(row[4] for row in matches)
        weights = np.asarray(
            [2 ** (-max(0.0, (reference - row[4]).total_seconds() / 86_400) / half_life_days) for row in matches]
        )
        untimed = [(home, away, hg, ag) for home, away, hg, ag, _ in matches]
        return self._fit(untimed, weights)

    def _fit(self, matches: list[tuple[str, str, int, int]], weights: np.ndarray) -> Self:
        if not matches:
            raise ValueError("At least one completed match is required")
        teams = sorted({row[0] for row in matches} | {row[1] for row in matches})
        index = {team: position for position, team in enumerate(teams)}
        home = np.asarray([index[row[0]] for row in matches], dtype=int)
        away = np.asarray([index[row[1]] for row in matches], dtype=int)
        home_goals = np.asarray([row[2] for row in matches], dtype=float)
        away_goals = np.asarray([row[3] for row in matches], dtype=float)
        count = len(teams)
        initial = np.zeros(count * 2 + 2)
        initial[-2] = np.log(max(float(np.mean(np.r_[home_goals, away_goals])), 0.1))

        def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
            attack = parameters[:count] - np.mean(parameters[:count])
            defense = parameters[count : count * 2] - np.mean(parameters[count : count * 2])
            intercept, home_effect = parameters[-2:]
            home_rate = np.exp(intercept + home_effect + attack[home] + defense[away])
            away_rate = np.exp(intercept + attack[away] + defense[home])
            log_likelihood = (
                home_goals * np.log(home_rate)
                - home_rate
                - gammaln(home_goals + 1)
                + away_goals * np.log(away_rate)
                - away_rate
                - gammaln(away_goals + 1)
            )
            penalty = self.regularization * float(np.sum(attack**2) + np.sum(defense**2))
            residual_home = weights * (home_rate - home_goals)
            residual_away = weights * (away_rate - away_goals)
            attack_gradient = np.zeros(count)
            defense_gradient = np.zeros(count)
            np.add.at(attack_gradient, home, residual_home)
            np.add.at(attack_gradient, away, residual_away)
            np.add.at(defense_gradient, away, residual_home)
            np.add.at(defense_gradient, home, residual_away)
            attack_gradient += 2 * self.regularization * attack
            defense_gradient += 2 * self.regularization * defense
            attack_gradient -= np.mean(attack_gradient)
            defense_gradient -= np.mean(defense_gradient)
            gradient = np.r_[
                attack_gradient,
                defense_gradient,
                float(np.sum(residual_home + residual_away)),
                float(np.sum(residual_home)),
            ]
            return -float(np.sum(weights * log_likelihood)) + penalty, gradient

        fitted = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            jac=True,
            options={"maxiter": 2_000, "maxfun": 100_000, "ftol": 1e-9},
        )
        if not fitted.success:
            raise RuntimeError(f"Poisson optimization failed: {fitted.message}")
        attack = fitted.x[:count] - np.mean(fitted.x[:count])
        defense = fitted.x[count : count * 2] - np.mean(fitted.x[count : count * 2])
        self.team_attack = dict(zip(teams, attack, strict=True))
        self.team_defense = dict(zip(teams, defense, strict=True))
        self.intercept = float(fitted.x[-2])
        self.home_advantage = float(fitted.x[-1])
        self.fitted_teams = tuple(teams)
        return self

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        home_rate = np.exp(
            self.intercept + self.home_advantage + self.team_attack.get(home, 0.0) + self.team_defense.get(away, 0.0)
        )
        away_rate = np.exp(self.intercept + self.team_attack.get(away, 0.0) + self.team_defense.get(home, 0.0))
        return float(home_rate), float(away_rate)

    def score_matrix(self, home: str, away: str) -> np.ndarray:
        home_rate, away_rate = self.expected_goals(home, away)
        return ScoreDistribution.poisson(home_rate, away_rate).probabilities

    def predict_proba(self, fixtures: list[tuple[str, str]]) -> np.ndarray:
        rows = []
        for home, away in fixtures:
            matrix = self.score_matrix(home, away)
            rows.append([np.tril(matrix, -1).sum(), np.trace(matrix), np.triu(matrix, 1).sum()])
        return np.asarray(rows)

    def market_probabilities(self, home: str, away: str) -> dict[str, float]:
        matrix = self.score_matrix(home, away)
        indices = np.indices(matrix.shape)
        total_goals = indices[0] + indices[1]
        btts = (indices[0] > 0) & (indices[1] > 0)
        return {
            "over_2_5": float(matrix[total_goals >= 3].sum()),
            "under_2_5": float(matrix[total_goals <= 2].sum()),
            "btts_yes": float(matrix[btts].sum()),
            "btts_no": float(matrix[~btts].sum()),
        }

    def correct_score_probabilities(self, home: str, away: str) -> dict[str, float]:
        matrix = self.score_matrix(home, away)
        return {
            f"{home_goals}-{away_goals}": float(matrix[home_goals, away_goals])
            for home_goals in range(matrix.shape[0])
            for away_goals in range(matrix.shape[1])
        }

    def save(self, path: Path) -> None:
        save_pickle(self, path, self.metadata())

    @classmethod
    def load(cls, path: Path) -> Self:
        value = load_pickle(path)
        if not isinstance(value, cls):
            raise TypeError("Artifact is not a PoissonModel")
        return value

    def metadata(self) -> dict[str, Any]:
        return {
            "model_type": "poisson",
            "maximum_goals": self.maximum_goals,
            "regularization": self.regularization,
            "teams": len(self.fitted_teams),
            "competitions": len(getattr(self, "fitted_competitions", ())),
            "intercept": self.intercept,
            "home_advantage": self.home_advantage,
        }
