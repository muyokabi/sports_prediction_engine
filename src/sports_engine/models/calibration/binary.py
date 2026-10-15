"""Calibration for direct binary market-family probability models."""

from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


@dataclass
class BinaryProbabilityCalibrator:
    method: str
    random_seed: int = 20261007
    estimator: object | None = None

    def fit(self, probabilities: np.ndarray, targets: np.ndarray) -> "BinaryProbabilityCalibrator":
        predicted = np.asarray(probabilities, dtype=float)
        observed = np.asarray(targets, dtype=int)
        if self.method not in {"platt", "isotonic"}:
            raise ValueError("Calibration method must be 'platt' or 'isotonic'")
        if predicted.ndim != 1 or not len(predicted) or len(predicted) != len(observed):
            raise ValueError("Binary calibration requires aligned non-empty vectors")
        if not np.isfinite(predicted).all() or (predicted < 0).any() or (predicted > 1).any():
            raise ValueError("Binary calibration probabilities are invalid")
        if set(np.unique(observed)) != {0, 1}:
            raise ValueError("Binary calibration holdout must contain both classes")
        if self.method == "platt":
            estimator: object = LogisticRegression(random_state=self.random_seed)
            estimator.fit(self._logit(predicted).reshape(-1, 1), observed)  # type: ignore[attr-defined]
        else:
            estimator = IsotonicRegression(out_of_bounds="clip")
            estimator.fit(predicted, observed)  # type: ignore[attr-defined]
        self.estimator = estimator
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        if self.estimator is None:
            raise ValueError("Calibrator has not been fitted")
        predicted = np.asarray(probabilities, dtype=float)
        if self.method == "platt":
            calibrated = self.estimator.predict_proba(self._logit(predicted).reshape(-1, 1))[:, 1]  # type: ignore[attr-defined]
        else:
            calibrated = self.estimator.predict(predicted)  # type: ignore[attr-defined]
        values = np.asarray(calibrated, dtype=float)
        if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
            raise ValueError("Binary calibrator produced invalid probabilities")
        return values

    @staticmethod
    def _logit(values: np.ndarray) -> np.ndarray:
        clipped = np.clip(values, 1e-8, 1 - 1e-8)
        return np.log(clipped / (1 - clipped))
