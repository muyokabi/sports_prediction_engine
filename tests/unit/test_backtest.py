import pytest

from sports_engine.evaluation.backtest import select_value_decision


def test_backtest_requires_probability_difference_and_positive_expected_value() -> None:
    probabilities = {"home": 0.55, "draw": 0.25, "away": 0.20}
    fair = {"home": 0.45, "draw": 0.28, "away": 0.27}
    decision = select_value_decision(
        probabilities,
        fair,
        {"home": 2.1, "draw": 3.5, "away": 4.0},
        minimum_probability_difference=0.03,
        minimum_expected_value=0.0,
    )
    assert decision is not None
    assert decision[:2] == ("home", 2.1)
    assert decision[2] == pytest.approx(0.155)
    assert (
        select_value_decision(
            probabilities,
            fair,
            {"home": 1.5, "draw": 3.5, "away": 4.0},
            minimum_probability_difference=0.03,
            minimum_expected_value=0.0,
        )
        is None
    )
