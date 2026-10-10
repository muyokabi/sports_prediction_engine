from dataclasses import dataclass
from math import ceil, sqrt

import numpy as np


@dataclass(frozen=True, slots=True)
class MetricUncertainty:
    estimate: float
    lower: float
    upper: float
    samples: int
    method: str


def per_fixture_loss(y_true: np.ndarray, probabilities: np.ndarray, metric: str) -> np.ndarray:
    encoded = np.eye(probabilities.shape[1])[y_true]
    if metric == "log_loss":
        return -np.log(np.clip(probabilities[np.arange(len(y_true)), y_true], 1e-15, 1.0))
    if metric == "brier":
        return np.sum((probabilities - encoded) ** 2, axis=1)
    if metric == "rps":
        return np.sum(
            (np.cumsum(probabilities, axis=1)[:, :-1] - np.cumsum(encoded, axis=1)[:, :-1]) ** 2,
            axis=1,
        ) / (probabilities.shape[1] - 1)
    raise ValueError(f"Unsupported probability metric {metric!r}")


def chronological_block_bootstrap(
    values: np.ndarray,
    *,
    samples: int = 2_000,
    confidence: float = 0.95,
    seed: int = 0,
    block_size: int | None = None,
) -> MetricUncertainty:
    """Bootstrap a chronological mean with contiguous blocks.

    The interval describes sampling uncertainty only; it is not a prediction
    interval and must not be presented as one.
    """
    rows = np.asarray(values, dtype=float)
    if rows.ndim != 1 or not len(rows):
        raise ValueError("values must be a non-empty one-dimensional array")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    width = block_size or max(1, int(sqrt(len(rows))))
    width = min(width, len(rows))
    starts = np.arange(len(rows) - width + 1)
    blocks_needed = ceil(len(rows) / width)
    rng = np.random.default_rng(seed)
    estimates = np.empty(samples)
    for index in range(samples):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate([rows[start : start + width] for start in selected])[: len(rows)]
        estimates[index] = sample.mean()
    alpha = (1 - confidence) / 2
    return MetricUncertainty(
        float(rows.mean()),
        float(np.quantile(estimates, alpha)),
        float(np.quantile(estimates, 1 - alpha)),
        samples,
        f"chronological-block-bootstrap(block_size={width})",
    )


def paired_metric_difference(
    y_true: np.ndarray,
    candidate: np.ndarray,
    comparator: np.ndarray,
    metric: str,
    *,
    samples: int = 2_000,
    confidence: float = 0.95,
    seed: int = 0,
    block_size: int | None = None,
) -> MetricUncertainty:
    difference = per_fixture_loss(y_true, candidate, metric) - per_fixture_loss(y_true, comparator, metric)
    return chronological_block_bootstrap(
        difference,
        samples=samples,
        confidence=confidence,
        seed=seed,
        block_size=block_size,
    )
