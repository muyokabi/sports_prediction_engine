import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from sports_engine.evaluation.comparison import compare_evaluation_reports


def _report(tmp_path: Path, model_type: str, probabilities: list[list[float]]) -> Path:
    rows = len(probabilities)
    prediction_path = tmp_path / f"{model_type}.predictions.parquet"
    pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(rows)],
            "prediction_timestamp": [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(rows)],
            "fold": [1] * rows,
            "target": [index % 3 for index in range(rows)],
            "home_probability": [row[0] for row in probabilities],
            "draw_probability": [row[1] for row in probabilities],
            "away_probability": [row[2] for row in probabilities],
        }
    ).write_parquet(prediction_path)
    raw = prediction_path.read_bytes()
    path = tmp_path / f"{model_type}.json"
    path.write_text(
        json.dumps(
            {
                "model_type": model_type,
                "candidate_version": f"{model_type}-version",
                "candidate_training_mode": "full_refit",
                "dataset_hash": "same-dataset-hash",
                "aggregate_metrics": {
                    "log_loss": 1.0,
                    "brier": 0.6,
                    "rps": 0.2,
                    "expected_calibration_error": 0.02,
                },
                "prediction_artifact": {
                    "path": str(prediction_path),
                    "rows": rows,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_paired_comparison_uses_identical_out_of_fold_predictions(tmp_path: Path) -> None:
    rows = 60
    informed = [
        [0.8, 0.1, 0.1] if index % 3 == 0 else [0.1, 0.8, 0.1] if index % 3 == 1 else [0.1, 0.1, 0.8]
        for index in range(rows)
    ]
    uniform = [[1 / 3, 1 / 3, 1 / 3] for _ in range(rows)]
    candidate = _report(tmp_path, "candidate", informed)
    comparator = _report(tmp_path, "comparator", uniform)

    result_path = compare_evaluation_reports([candidate, comparator], tmp_path / "comparisons", random_seed=7)

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["comparisons"][0]["verdict"] == "CANDIDATE_DOMINATES"
    assert payload["comparisons"][0]["rows"] == rows
