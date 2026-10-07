import numpy as np


def weighted_probabilities(predictions: list[np.ndarray], weights: list[float]) -> np.ndarray:
    if len(predictions) != len(weights) or not predictions:
        raise ValueError("Predictions and weights must be non-empty and have equal length")
    normalized = np.asarray(weights, dtype=float)
    if np.any(normalized < 0) or normalized.sum() <= 0:
        raise ValueError("Weights must be non-negative with positive mass")
    normalized /= normalized.sum()
    result = np.average(np.stack(predictions), axis=0, weights=normalized)
    return result / result.sum(axis=1, keepdims=True)
