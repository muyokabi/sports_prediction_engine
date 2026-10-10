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
        "probability_integrity": probability_integrity(probabilities),
    }


def probability_integrity(probabilities: np.ndarray) -> dict[str, Any]:
    """Audit probability geometry independently of realized outcomes."""
    matrix = np.asarray(probabilities, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != 3 or not len(matrix):
        return {"passed": False, "reasons": ["INVALID_PROBABILITY_SHAPE"]}
    reasons: list[str] = []
    if not np.isfinite(matrix).all():
        reasons.append("NON_FINITE_PROBABILITY")
    if (matrix < 0).any() or (matrix > 1).any():
        reasons.append("PROBABILITY_OUT_OF_BOUNDS")
    normalization_error = float(np.max(np.abs(matrix.sum(axis=1) - 1.0)))
    if normalization_error > 1e-8:
        reasons.append("PROBABILITIES_NOT_NORMALIZED")
    rounded = np.round(matrix, 6)
    unique_rows, counts = np.unique(rounded, axis=0, return_counts=True)
    clipped = np.clip(matrix, 1e-15, 1.0)
    entropy = -np.sum(clipped * np.log(clipped), axis=1)
    return {
        "passed": not reasons,
        "reasons": reasons,
        "rows": len(matrix),
        "maximum_normalization_error": normalization_error,
        "minimum_probability": float(np.nanmin(matrix)),
        "maximum_probability": float(np.nanmax(matrix)),
        "unique_vectors_at_6dp": len(unique_rows),
        "unique_vector_fraction": len(unique_rows) / len(matrix),
        "largest_duplicate_cluster": int(counts.max()),
        "mean_entropy": float(np.mean(entropy)),
        "minimum_entropy": float(np.min(entropy)),
    }
