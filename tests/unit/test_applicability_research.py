import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from sports_engine.evaluation.applicability_research import evaluate_applicability_discrimination


def _source(tmp_path: Path, *, tamper: bool = False) -> Path:
    rows = 400
    accepted = np.tile([True] * 50 + [False] * 50, 4)
    targets = np.arange(rows) % 3
    probabilities = np.zeros((rows, 3), dtype=float)
    probabilities[:] = 0.1
    probabilities[np.arange(rows), targets] = np.where(accepted, 0.8, 0.4)
    probabilities[np.arange(rows), (targets + 1) % 3] = np.where(accepted, 0.1, 0.3)
    probabilities[np.arange(rows), (targets + 2) % 3] = np.where(accepted, 0.1, 0.3)
    frame = pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(rows)],
            "prediction_timestamp": [
                datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(rows)
            ],
            "fold": np.repeat([1, 2, 3, 4], rows // 4),
            "target": targets,
            "home_probability": probabilities[:, 0],
            "draw_probability": probabilities[:, 1],
            "away_probability": probabilities[:, 2],
            "home_effective_training_matches": np.where(accepted, 8.0, 2.0),
            "away_effective_training_matches": np.where(accepted, 7.0, 1.0),
        }
    )
    predictions = tmp_path / "source.predictions.parquet"
    frame.write_parquet(predictions)
    raw = predictions.read_bytes()
    report = tmp_path / "source.json"
    report.write_text(
        json.dumps(
            {
                "dataset_hash": "dataset-hash",
                "candidate_version": "candidate-version",
                "prediction_artifact": {
                    "path": str(predictions),
                    "rows": rows,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    if tamper:
        predictions.write_bytes(raw + b"tampered")
    return report


def test_applicability_audit_requires_stable_fold_discrimination(tmp_path: Path) -> None:
    result = evaluate_applicability_discrimination(
        _source(tmp_path),
        tmp_path / "evaluation",
        random_seed=7,
        minimum_group_rows=40,
    )
    payload = json.loads(result.read_text(encoding="utf-8"))

    assert payload["discriminatively_validated"] is True
    assert payload["contract"]["promotion_permitted"] is False
    assert payload["aggregate"]["accepted_rows"] == 200
    assert all(
        item["accepted_minus_rejected"]["log_loss"]["upper"] < 0
        for item in payload["fold_results"]
    )


def test_applicability_audit_rejects_tampered_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="digest"):
        evaluate_applicability_discrimination(
            _source(tmp_path, tamper=True),
            tmp_path / "evaluation",
            random_seed=7,
        )


def test_applicability_audit_rejects_invalid_threshold(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        evaluate_applicability_discrimination(
            _source(tmp_path),
            tmp_path / "evaluation",
            random_seed=7,
            minimum_effective_matches=float("nan"),
        )
