from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


@dataclass
class MulticlassProbabilityCalibrator:
    method: str
    random_seed: int = 20261007
    estimators: list[object] = field(default_factory=list)

    def fit(self, probabilities: np.ndarray, targets: np.ndarray) -> "MulticlassProbabilityCalibrator":
        if self.method not in {"platt", "isotonic"}:
            raise ValueError("Calibration method must be 'platt' or 'isotonic'")
        if probabilities.ndim != 2 or probabilities.shape[1] != 3:
            raise ValueError("Expected an N x 3 probability matrix")
        self.estimators = []
        for class_index in range(3):
            binary = (targets == class_index).astype(int)
            if len(np.unique(binary)) != 2:
                raise ValueError("Calibration holdout must contain every outcome class")
            if self.method == "platt":
                estimator: object = LogisticRegression(random_state=self.random_seed)
                estimator.fit(self._logit(probabilities[:, class_index]).reshape(-1, 1), binary)  # type: ignore[attr-defined]
            else:
                estimator = IsotonicRegression(out_of_bounds="clip")
                estimator.fit(probabilities[:, class_index], binary)  # type: ignore[attr-defined]
            self.estimators.append(estimator)
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        if len(self.estimators) != 3:
            raise ValueError("Calibrator has not been fitted")
        columns = []
        for index, estimator in enumerate(self.estimators):
            if self.method == "platt":
                values = estimator.predict_proba(  # type: ignore[attr-defined]
                    self._logit(probabilities[:, index]).reshape(-1, 1)
                )[:, 1]
            else:
                values = estimator.predict(probabilities[:, index])  # type: ignore[attr-defined]
            columns.append(values)
        calibrated = np.column_stack(columns)
        if not np.all(np.isfinite(calibrated)):
            raise ValueError("Calibrator produced non-finite probabilities")
        if np.any(calibrated < 0):
            raise ValueError("Calibrator produced negative probabilities")
        totals = calibrated.sum(axis=1, keepdims=True)
        if np.any(totals <= 0):
            raise ValueError("Calibrator produced zero probability mass")
        normalized = calibrated / totals
        if not np.allclose(normalized.sum(axis=1), 1.0):
            raise ValueError("Calibrated probabilities do not form a simplex")
        return normalized

    @staticmethod
    def _logit(values: np.ndarray) -> np.ndarray:
        clipped = np.clip(values, 1e-8, 1 - 1e-8)
        return np.log(clipped / (1 - clipped))
