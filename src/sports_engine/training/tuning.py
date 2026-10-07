from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import log_loss


@dataclass(frozen=True, slots=True)
class TuningResult:
    model: Any
    hyperparameters: dict[str, Any]
    validation_log_loss: float


def constrained_probability_search(
    candidates: list[tuple[dict[str, Any], Callable[[], Any]]],
    train_features: np.ndarray,
    train_targets: np.ndarray,
    validation_features: np.ndarray,
    validation_targets: np.ndarray,
) -> TuningResult:
    if not candidates:
        raise ValueError("At least one tuning candidate is required")
    best: TuningResult | None = None
    for hyperparameters, factory in candidates:
        model = factory()
        model.fit(train_features, train_targets)
        probabilities = model.predict_proba(validation_features)
        score = float(log_loss(validation_targets, probabilities, labels=[0, 1, 2]))
        if best is None or score < best.validation_log_loss:
            best = TuningResult(model, hyperparameters, score)
    assert best is not None
    return best
