import numpy as np
import pytest

from sports_engine.markets.consensus import consensus
from sports_engine.markets.implied_probability import no_vig_probabilities
from sports_engine.markets.overround import overround


def test_three_way_no_vig_probabilities_sum_to_one() -> None:
    odds = [2.2, 3.4, 3.5]
    assert no_vig_probabilities(odds).sum() == pytest.approx(1.0)
    assert overround(odds) > 1.0


def test_consensus_uses_robust_median_then_renormalizes() -> None:
    result = consensus([[0.5, 0.25, 0.25], [0.48, 0.27, 0.25], [0.9, 0.05, 0.05]])
    assert result.sum() == pytest.approx(1.0)
    assert np.argmax(result) == 0
