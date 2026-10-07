from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from sports_engine.models.serialization import load_pickle, save_pickle


@dataclass
class LogisticProbabilityModel:
    random_seed: int = 20261007
    c: float = 1.0

    def __post_init__(self) -> None:
        self.estimator = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=self.c,
                        max_iter=1000,
                        class_weight="balanced",
                        random_state=self.random_seed,
                    ),
                ),
            ]
        )

    def fit(self, features: np.ndarray, targets: np.ndarray) -> Self:
        self.estimator.fit(features, targets)
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return self.estimator.predict_proba(features)

    def save(self, path: Path) -> None:
        save_pickle(self, path, self.metadata())

    @classmethod
    def load(cls, path: Path) -> Self:
        value = load_pickle(path)
        if not isinstance(value, cls):
            raise TypeError("Artifact is not a LogisticProbabilityModel")
        return value

    def metadata(self) -> dict[str, Any]:
        return {"model_type": "logistic", "random_seed": self.random_seed, "C": self.c}
