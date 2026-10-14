import numpy as np
import pytest

from sports_engine.evaluation.metrics import binary_probability_metrics
from sports_engine.evaluation.uncertainty import binary_per_fixture_loss


def test_binary_metrics_use_event_probability_not_top_label_confidence() -> None:
    targets = np.asarray([0, 0, 1, 1])
    probabilities = np.asarray([0.1, 0.2, 0.8, 0.9])

    metrics = binary_probability_metrics(targets, probabilities, bins=2)

    assert metrics["brier"] == pytest.approx(0.025)
    assert metrics["expected_calibration_error"] == pytest.approx(0.15)
    assert metrics["probability_integrity"]["passed"] is True
    assert binary_per_fixture_loss(targets, probabilities, "brier").tolist() == pytest.approx(
        [0.01, 0.04, 0.04, 0.01]
    )


@pytest.mark.parametrize(
    "probabilities",
    [np.asarray([0.2, np.nan]), np.asarray([0.2, -0.1]), np.asarray([0.2, 1.1])],
)
def test_binary_metrics_reject_invalid_probability_output(probabilities: np.ndarray) -> None:
    with pytest.raises(ValueError, match="Invalid binary probabilities"):
        binary_probability_metrics(np.asarray([0, 1]), probabilities)
