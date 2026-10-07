import numpy as np


def probability_delta(model: list[float], market: list[float]) -> np.ndarray:
    left = np.asarray(model, dtype=float)
    right = np.asarray(market, dtype=float)
    if left.shape != right.shape:
        raise ValueError("Model and market probability shapes differ")
    return left - right
