import numpy as np


def raw_implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        raise ValueError("Decimal odds must be greater than 1")
    return 1.0 / decimal_odds


def no_vig_probabilities(decimal_odds: list[float]) -> np.ndarray:
    raw = np.asarray([raw_implied_probability(value) for value in decimal_odds], dtype=float)
    total = raw.sum()
    if total <= 0:
        raise ValueError("Market implied probabilities must have positive mass")
    return raw / total
