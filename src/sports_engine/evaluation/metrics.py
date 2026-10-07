from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, log_loss


def multiclass_brier(y_true: np.ndarray, probabilities: np.ndarray, classes: int = 3) -> float:
    encoded = np.eye(classes)[y_true]
    return float(np.mean(np.sum((probabilities - encoded) ** 2, axis=1)))


def ranked_probability_score(y_true: np.ndarray, probabilities: np.ndarray, classes: int = 3) -> float:
    encoded = np.eye(classes)[y_true]
    return float(
        np.mean(
            np.sum(
                (np.cumsum(probabilities, axis=1)[:, :-1] - np.cumsum(encoded, axis=1)[:, :-1]) ** 2,
                axis=1,
            )
            / (classes - 1)
        )
    )


def expected_calibration_error(y_true: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> float:
    predictions = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    correct = predictions == y_true
    error = 0.0
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    for lower, upper in zip(boundaries[:-1], boundaries[1:], strict=True):
        members = (confidence > lower) & (confidence <= upper)
        if members.any():
            error += float(members.mean()) * abs(float(correct[members].mean()) - float(confidence[members].mean()))
    return error


def calibration_curve_data(
    y_true: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> dict[str, list[dict[str, float | int]]]:
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    result: dict[str, list[dict[str, float | int]]] = {}
    for class_index, label in enumerate(("home", "draw", "away")):
        observed = y_true == class_index
        points: list[dict[str, float | int]] = []
        for lower, upper in zip(boundaries[:-1], boundaries[1:], strict=True):
            members = (probabilities[:, class_index] > lower) & (probabilities[:, class_index] <= upper)
            if members.any():
                points.append(
                    {
                        "mean_predicted": float(probabilities[members, class_index].mean()),
                        "observed_frequency": float(observed[members].mean()),
                        "count": int(members.sum()),
                    }
                )
        result[label] = points
    return result


def probability_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    predictions = probabilities.argmax(axis=1)
    return {
        "log_loss": float(log_loss(y_true, probabilities, labels=[0, 1, 2])),
        "brier": multiclass_brier(y_true, probabilities),
        "rps": ranked_probability_score(y_true, probabilities),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "expected_calibration_error": expected_calibration_error(y_true, probabilities),
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=[0, 1, 2]).tolist(),
        "calibration_curves": calibration_curve_data(y_true, probabilities),
    }
