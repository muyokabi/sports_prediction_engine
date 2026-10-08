from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import lightgbm as lgb
import numpy as np

from sports_engine.models.serialization import load_pickle, save_pickle


@dataclass
class LightGBMProbabilityModel:
    random_seed: int = 20261007
    threads: int = 2
    n_estimators: int = 300

    def __post_init__(self) -> None:
        self.estimator = lgb.LGBMClassifier(
            objective="multiclass",
            n_estimators=self.n_estimators,
            num_leaves=31,
            learning_rate=0.05,
            random_state=self.random_seed,
            n_jobs=self.threads,
            verbosity=-1,
        )

    def fit(self, features: np.ndarray, targets: np.ndarray) -> Self:
        self.estimator.fit(features, targets)
        return self

    def fit_incremental(self, features: np.ndarray, targets: np.ndarray, parent: "LightGBMProbabilityModel") -> Self:
        self.estimator.fit(features, targets, init_model=parent.estimator.booster_)
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return np.asarray(self.estimator.predict_proba(features))

    def save(self, path: Path) -> None:
        save_pickle(self, path, self.metadata())

    @classmethod
    def load(cls, path: Path) -> Self:
        value = load_pickle(path)
        if not isinstance(value, cls):
            raise TypeError("Artifact is not a LightGBMProbabilityModel")
        return value

    def metadata(self) -> dict[str, Any]:
        return {
            "model_type": "lightgbm",
            "n_estimators": self.n_estimators,
            "threads": self.threads,
        }
