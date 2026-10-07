import pytest

from sports_engine.models.statistical.poisson import PoissonModel


def test_home_win_triangle_is_not_reversed() -> None:
    matches = [("Strong", "Weak", 4, 0)] * 8 + [("Weak", "Strong", 0, 2)] * 8
    probabilities = PoissonModel().fit(matches).predict_proba([("Strong", "Weak")])[0]
    assert probabilities.sum() == pytest.approx(1.0)
    assert probabilities[0] > probabilities[2]
