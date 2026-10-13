import numpy as np
from scipy.optimize import brentq


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


def no_vig_double_chance_probabilities(decimal_odds: list[float]) -> np.ndarray:
    """Proportionally de-vig a complete three-way double-chance book.

    HOME/DRAW, HOME/AWAY, and DRAW/AWAY overlap: every underlying 1X2
    outcome appears in exactly two selections.  Their coherent fair
    probabilities therefore sum to two, not one.
    """
    if len(decimal_odds) != 3:
        raise ValueError("Double chance de-vig requires all three selections")
    raw = np.asarray([raw_implied_probability(value) for value in decimal_odds], dtype=float)
    total = raw.sum()
    if total <= 0:
        raise ValueError("Market implied probabilities must have positive mass")
    return raw * (2.0 / total)


def power_probabilities(decimal_odds: list[float]) -> np.ndarray:
    raw = np.asarray([raw_implied_probability(value) for value in decimal_odds], dtype=float)
    if len(raw) < 2:
        raise ValueError("A mutually exclusive market needs at least two prices")
    exponent = brentq(lambda value: float(np.power(raw, value).sum() - 1), 1e-9, 100.0)
    probabilities = np.power(raw, exponent)
    return probabilities / probabilities.sum()


def shin_probabilities(decimal_odds: list[float]) -> np.ndarray:
    raw = np.asarray([raw_implied_probability(value) for value in decimal_odds], dtype=float)
    margin = float(raw.sum())
    if len(raw) < 2:
        raise ValueError("A mutually exclusive market needs at least two prices")
    if margin <= 1:
        return raw / margin

    def probabilities(z: float) -> np.ndarray:
        return (np.sqrt(z * z + 4 * (1 - z) * raw * raw / margin) - z) / (2 * (1 - z))

    insider = brentq(lambda value: float(probabilities(value).sum() - 1), 0.0, 1 - 1e-12)
    result = probabilities(insider)
    return result / result.sum()
