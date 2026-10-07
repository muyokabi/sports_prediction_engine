from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from sports_engine.models.calibration.multiclass import MulticlassProbabilityCalibrator
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.elo import EloModel
from sports_engine.models.statistical.poisson import PoissonModel

MATCHES = [("A", "B", 2, 0), ("B", "A", 1, 1), ("A", "C", 3, 1), ("C", "B", 0, 1)]


def test_elo_returns_normalized_three_way_probabilities() -> None:
    probabilities = EloModel().fit(MATCHES).predict_proba([("A", "B")])
    assert probabilities.shape == (1, 3)
    assert np.allclose(probabilities.sum(axis=1), 1)


def test_poisson_exposes_result_and_secondary_markets() -> None:
    model = PoissonModel().fit(MATCHES)
    assert np.allclose(model.predict_proba([("A", "B")]).sum(axis=1), 1)
    markets = model.market_probabilities("A", "B")
    assert markets["over_2_5"] + markets["under_2_5"] == pytest.approx(1.0)
    assert sum(model.correct_score_probabilities("A", "B").values()) == pytest.approx(1.0)


def test_poisson_supports_time_decay_and_dixon_coles_low_score_correction() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    timed = [(*match, base + timedelta(days=index)) for index, match in enumerate(MATCHES)]
    poisson = PoissonModel().fit_timed(timed, half_life_days=30)
    dixon_coles = DixonColesModel().fit(MATCHES)
    assert poisson.expected_goals("A", "B")[0] > 0
    assert dixon_coles.rho != -0.1
    assert dixon_coles.score_matrix("A", "B").sum() == pytest.approx(1.0)


def test_model_serialization_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "elo.pkl"
    original = EloModel().fit(MATCHES)
    original.save(path)
    restored = EloModel.load(path)
    assert np.allclose(original.predict_proba([("A", "B")]), restored.predict_proba([("A", "B")]))


@pytest.mark.parametrize("method", ["platt", "isotonic"])
def test_multiclass_calibration_preserves_probability_simplex(method: str) -> None:
    probabilities = np.asarray(
        [
            [0.7, 0.2, 0.1],
            [0.6, 0.3, 0.1],
            [0.5, 0.2, 0.3],
            [0.2, 0.6, 0.2],
            [0.1, 0.7, 0.2],
            [0.3, 0.5, 0.2],
            [0.2, 0.2, 0.6],
            [0.1, 0.2, 0.7],
            [0.3, 0.2, 0.5],
        ]
    )
    targets = np.asarray([0, 0, 0, 1, 1, 1, 2, 2, 2])
    calibrated = (
        MulticlassProbabilityCalibrator(method, random_seed=7).fit(probabilities, targets).transform(probabilities)
    )
    assert calibrated.shape == probabilities.shape
    assert np.allclose(calibrated.sum(axis=1), 1.0)
    assert np.all((calibrated >= 0) & (calibrated <= 1))
