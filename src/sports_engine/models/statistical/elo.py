from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import numpy as np

from sports_engine.models.serialization import load_pickle, save_pickle


@dataclass
class EloModel:
    k_factor: float = 20.0
    home_advantage: float = 60.0
    initial_rating: float = 1500.0
    draw_probability: float = 0.25
    ratings: dict[str, float] = field(default_factory=dict)

    def _rating(self, team: str) -> float:
        return self.ratings.get(team, self.initial_rating)

    def fit(self, matches: list[tuple[str, str, int, int]]) -> Self:
        for home, away, home_goals, away_goals in matches:
            home_rating = self._rating(home)
            away_rating = self._rating(away)
            expected_home = 1.0 / (1.0 + 10 ** ((away_rating - home_rating - self.home_advantage) / 400))
            actual_home = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
            change = self.k_factor * (actual_home - expected_home)
            self.ratings[home] = home_rating + change
            self.ratings[away] = away_rating - change
        return self

    def predict_proba(self, fixtures: list[tuple[str, str]]) -> np.ndarray:
        rows = []
        for home, away in fixtures:
            decisive_home = 1.0 / (1.0 + 10 ** ((self._rating(away) - self._rating(home) - self.home_advantage) / 400))
            decisive_mass = 1.0 - self.draw_probability
            rows.append(
                [
                    decisive_home * decisive_mass,
                    self.draw_probability,
                    (1.0 - decisive_home) * decisive_mass,
                ]
            )
        return np.asarray(rows)

    def save(self, path: Path) -> None:
        save_pickle(self, path, self.metadata())

    @classmethod
    def load(cls, path: Path) -> Self:
        value = load_pickle(path)
        if not isinstance(value, cls):
            raise TypeError("Artifact is not an EloModel")
        return value

    def metadata(self) -> dict[str, Any]:
        return {
            "model_type": "elo",
            "k_factor": self.k_factor,
            "home_advantage": self.home_advantage,
            "teams": len(self.ratings),
        }
