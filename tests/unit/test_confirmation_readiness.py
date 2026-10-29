import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl

from sports_engine.evaluation.confirmation_readiness import evaluate_confirmation_readiness


def test_confirmation_readiness_rejects_tiny_later_era(tmp_path: Path) -> None:
    connection = _connection_with_datasets(tmp_path, added_rows=5)
    path = evaluate_confirmation_readiness(
        connection,
        "baseline",
        "candidate",
        tmp_path / "results",
        minimum_new_rows=100,
    )
    connection.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready_for_confirmation_evaluation"] is False
    assert payload["reasons"] == ["INSUFFICIENT_GENUINELY_LATER_ROWS"]
    assert payload["delta"]["added_rows"] == 5
    assert payload["delta"]["genuinely_later_rows"] == 5
    assert payload["delta"]["removed_rows"] == 0
    assert payload["contract"]["promotion_eligible"] is False


def test_confirmation_readiness_detects_mutated_historical_target(tmp_path: Path) -> None:
    connection = _connection_with_datasets(tmp_path, added_rows=2, mutate_target=True)
    path = evaluate_confirmation_readiness(
        connection,
        "baseline",
        "candidate",
        tmp_path / "results",
        minimum_new_rows=1,
    )
    connection.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready_for_confirmation_evaluation"] is False
    assert "OVERLAPPING_TARGETS_CHANGED" in payload["reasons"]
    assert payload["delta"]["changed_overlapping_targets"] == 1


def test_confirmation_readiness_counts_only_strictly_later_rows(tmp_path: Path) -> None:
    connection = _connection_with_datasets(tmp_path, added_rows=100)
    candidate_path = _dataset_path(connection, "candidate")
    candidate = pl.read_parquet(candidate_path).with_columns(
        pl.when(pl.col("fixture_id") == "fixture-6")
        .then(datetime(2026, 1, 3, tzinfo=UTC))
        .otherwise(pl.col("prediction_timestamp"))
        .alias("prediction_timestamp")
    )
    candidate.write_parquet(candidate_path)

    path = evaluate_confirmation_readiness(
        connection,
        "baseline",
        "candidate",
        tmp_path / "results",
        minimum_new_rows=100,
    )
    connection.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready_for_confirmation_evaluation"] is False
    assert payload["delta"]["added_rows"] == 100
    assert payload["delta"]["genuinely_later_rows"] == 99
    assert payload["delta"]["non_later_added_rows"] == 1
    assert payload["reasons"] == [
        "INSUFFICIENT_GENUINELY_LATER_ROWS",
        "ADDITIONS_OVERLAP_PREVIOUSLY_INSPECTED_ERA",
    ]


def test_confirmation_readiness_detects_removed_rows(tmp_path: Path) -> None:
    connection = _connection_with_datasets(tmp_path, added_rows=2)
    candidate_path = _dataset_path(connection, "candidate")
    pl.read_parquet(candidate_path).filter(pl.col("fixture_id") != "fixture-2").write_parquet(
        candidate_path
    )

    path = evaluate_confirmation_readiness(
        connection,
        "baseline",
        "candidate",
        tmp_path / "results",
        minimum_new_rows=1,
    )
    connection.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready_for_confirmation_evaluation"] is False
    assert payload["delta"]["removed_rows"] == 1
    assert "BASELINE_ROWS_REMOVED" in payload["reasons"]


def test_confirmation_readiness_detects_target_changed_to_null(tmp_path: Path) -> None:
    connection = _connection_with_datasets(tmp_path, added_rows=2)
    candidate_path = _dataset_path(connection, "candidate")
    candidate = pl.read_parquet(candidate_path).with_columns(
        pl.when(pl.col("fixture_id") == "fixture-2")
        .then(pl.lit(None, dtype=pl.Int64))
        .otherwise(pl.col("target_home_goals"))
        .alias("target_home_goals")
    )
    candidate.write_parquet(candidate_path)

    path = evaluate_confirmation_readiness(
        connection,
        "baseline",
        "candidate",
        tmp_path / "results",
        minimum_new_rows=1,
    )
    connection.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ready_for_confirmation_evaluation"] is False
    assert payload["delta"]["changed_overlapping_targets"] == 1
    assert "OVERLAPPING_TARGETS_CHANGED" in payload["reasons"]


def _connection_with_datasets(
    tmp_path: Path,
    *,
    added_rows: int,
    mutate_target: bool = False,
) -> duckdb.DuckDBPyConnection:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    baseline_rows = 6
    baseline = _frame(started, baseline_rows)
    candidate = _frame(started, baseline_rows + added_rows)
    if mutate_target:
        candidate = candidate.with_columns(
            pl.when(pl.col("fixture_id") == "fixture-2")
            .then(pl.lit(9))
            .otherwise(pl.col("target_home_goals"))
            .alias("target_home_goals")
        )
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE feature_datasets(dataset_id VARCHAR, name VARCHAR, schema_hash VARCHAR, "
        "dataset_hash VARCHAR, parquet_path VARCHAR, config JSON, created_at TIMESTAMP)"
    )
    for name, frame in (("baseline", baseline), ("candidate", candidate)):
        path = tmp_path / f"{name}.parquet"
        frame.write_parquet(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        connection.execute(
            "INSERT INTO feature_datasets VALUES (?, ?, ?, ?, ?, ?, ?)",
            [name, name, "schema", digest, str(path), "{}", started],
        )
    return connection


def _frame(started: datetime, rows: int) -> pl.DataFrame:
    home_goals = [index % 3 for index in range(rows)]
    away_goals = [(index + 1) % 3 for index in range(rows)]
    return pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(rows)],
            "prediction_timestamp": [started + timedelta(days=index) for index in range(rows)],
            "home_team_id": [f"home-{index % 3}" for index in range(rows)],
            "away_team_id": [f"away-{index % 4}" for index in range(rows)],
            "target_home_goals": home_goals,
            "target_away_goals": away_goals,
            "target_result": [
                "HOME" if home > away else "DRAW" if home == away else "AWAY"
                for home, away in zip(home_goals, away_goals, strict=True)
            ],
        }
    )


def _dataset_path(connection: duckdb.DuckDBPyConnection, name: str) -> Path:
    row = connection.execute(
        "SELECT parquet_path FROM feature_datasets WHERE name=?",
        [name],
    ).fetchone()
    assert row is not None
    return Path(row[0])
