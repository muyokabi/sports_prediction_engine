import numpy as np


def consensus(probability_rows: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(probability_rows, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise ValueError("At least one bookmaker probability row is required")
    if not np.allclose(matrix.sum(axis=1), 1.0, atol=1e-8):
        raise ValueError("Each bookmaker row must sum to one")
    result = np.median(matrix, axis=0)
    return result / result.sum()
