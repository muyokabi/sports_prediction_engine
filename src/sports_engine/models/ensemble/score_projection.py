"""Coherent probability fusion built on an existing score distribution."""

import numpy as np


def convex_probability_blend(
    score_probabilities: np.ndarray,
    ml_probabilities: np.ndarray,
    *,
    ml_weight: float,
) -> np.ndarray:
    """Blend two aligned 1X2 probability matrices without inventing missing mass."""
    score = _validated_match_probabilities(score_probabilities, "score")
    ml = _validated_match_probabilities(ml_probabilities, "ml")
    if score.shape != ml.shape:
        raise ValueError("Score and ML probabilities must have identical shapes")
    if not 0.0 <= ml_weight <= 1.0:
        raise ValueError("ML weight must be between zero and one")
    blended = (1.0 - ml_weight) * score + ml_weight * ml
    return blended / blended.sum(axis=1, keepdims=True)


def project_match_odds_marginals(score_matrix: np.ndarray, match_probabilities: np.ndarray) -> np.ndarray:
    """Project target 1X2 marginals onto a score matrix.

    Each home/draw/away region is rescaled as a block. This exactly matches the
    requested 1X2 probabilities while preserving the score model's conditional
    distribution of scorelines within each outcome region.
    """
    matrix = np.asarray(score_matrix, dtype=float)
    target = np.asarray(match_probabilities, dtype=float)
    if matrix.ndim != 2 or not matrix.size:
        raise ValueError("Score matrix must be a non-empty two-dimensional matrix")
    if not np.isfinite(matrix).all() or (matrix < 0).any() or matrix.sum() <= 0:
        raise ValueError("Score matrix contains invalid probability mass")
    if target.shape != (3,) or not np.isfinite(target).all() or (target < 0).any():
        raise ValueError("Target match probabilities must be a finite three-vector")
    if not np.isclose(target.sum(), 1.0, atol=1e-8):
        raise ValueError("Target match probabilities must sum to one")

    normalized = matrix / matrix.sum()
    home_mask = np.tril(np.ones_like(normalized, dtype=bool), -1)
    draw_mask = np.eye(*normalized.shape).astype(bool)
    away_mask = np.triu(np.ones_like(normalized, dtype=bool), 1)
    projected = normalized.copy()
    for mask, probability in zip((home_mask, draw_mask, away_mask), target, strict=True):
        source_mass = float(normalized[mask].sum())
        if source_mass <= 0 and probability > 0:
            raise ValueError("Cannot project positive mass into an empty outcome region")
        projected[mask] *= probability / source_mass if source_mass else 0.0
    return projected / projected.sum()


def score_matrix_match_odds(score_matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(score_matrix, dtype=float)
    return np.asarray(
        [np.tril(matrix, -1).sum(), np.trace(matrix), np.triu(matrix, 1).sum()],
        dtype=float,
    )


def score_matrix_binary_markets(score_matrix: np.ndarray) -> tuple[float, float]:
    matrix = np.asarray(score_matrix, dtype=float)
    indexes = np.indices(matrix.shape)
    btts_yes = float(matrix[(indexes[0] > 0) & (indexes[1] > 0)].sum())
    over_2_5 = float(matrix[(indexes[0] + indexes[1]) >= 3].sum())
    return btts_yes, over_2_5


def _validated_match_probabilities(values: np.ndarray, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != 3 or not len(matrix):
        raise ValueError(f"{name} probabilities must be a non-empty Nx3 matrix")
    if not np.isfinite(matrix).all() or (matrix < 0).any() or (matrix > 1).any():
        raise ValueError(f"{name} probabilities contain invalid values")
    if not np.allclose(matrix.sum(axis=1), 1.0, atol=1e-8):
        raise ValueError(f"{name} probabilities must sum to one")
    return matrix
