from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import numpy as np
from catboost import CatBoostClassifier

from sports_engine.models.serialization import load_pickle, save_pickle


@dataclass
class CatBoostProbabilityModel:
    random_seed: int = 20261007
    threads: int = 2
    iterations: int = 300

    def __post_init__(self) -> None:
        self.estimator = CatBoostClassifier(
            loss_function="MultiClass",
            iterations=self.iterations,
            depth=6,
            learning_rate=0.05,
            random_seed=self.random_seed,
            thread_count=self.threads,
            verbose=False,
            allow_writing_files=False,
        )

    def fit(self, features: np.ndarray, targets: np.ndarray) -> Self:
        self.estimator.fit(features, targets)
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return np.asarray(self.estimator.predict_proba(features))

    def save(self, path: Path) -> None:
        save_pickle(self, path, self.metadata())

    @classmethod
    def load(cls, path: Path) -> Self:
        value = load_pickle(path)
        if not isinstance(value, cls):
            raise TypeError("Artifact is not a CatBoostProbabilityModel")
        return value

    def metadata(self) -> dict[str, Any]:
        return {"model_type": "catboost", "iterations": self.iterations, "threads": self.threads}
