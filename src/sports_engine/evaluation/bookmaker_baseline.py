import numpy as np

from sports_engine.evaluation.metrics import probability_metrics


def bookmaker_baseline_metrics(
    targets: np.ndarray, home: np.ndarray, draw: np.ndarray, away: np.ndarray
) -> dict[str, object] | None:
    probabilities = np.column_stack((home, draw, away)).astype(float)
    usable = np.isfinite(probabilities).all(axis=1) & (probabilities.sum(axis=1) > 0)
    if not usable.any():
        return None
    probabilities = probabilities[usable]
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    return {**probability_metrics(targets[usable], probabilities), "rows": int(usable.sum())}
