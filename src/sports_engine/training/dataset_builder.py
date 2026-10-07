import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl


@dataclass(frozen=True, slots=True)
class TrainingDataset:
    dataset_id: str
    name: str
    frame: pl.DataFrame
    schema_hash: str
    dataset_hash: str
    parquet_path: Path
    config: dict[str, Any]


def load_training_dataset(connection: duckdb.DuckDBPyConnection, dataset: str | None = None) -> TrainingDataset:
    if dataset:
        row = connection.execute(
            "SELECT CAST(dataset_id AS VARCHAR), name, schema_hash, dataset_hash, parquet_path, config "
            "FROM feature_datasets WHERE CAST(dataset_id AS VARCHAR)=? OR name=? "
            "ORDER BY created_at DESC LIMIT 1",
            [dataset, dataset],
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT CAST(dataset_id AS VARCHAR), name, schema_hash, dataset_hash, parquet_path, config "
            "FROM feature_datasets ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise ValueError("No matching feature dataset is registered; run `sports-engine features build` first")
    path = Path(row[4])
    if not path.is_file():
        raise ValueError(f"Registered feature dataset is missing: {path}")
    frame = pl.read_parquet(path)
    required = {
        "prediction_timestamp",
        "home_team_id",
        "away_team_id",
        "target_home_goals",
        "target_away_goals",
        "target_result",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Feature dataset is missing required columns: {sorted(missing)}")
    if frame.height < 5:
        raise ValueError("At least five completed fixtures are required for training")
    config = row[5] if isinstance(row[5], dict) else json.loads(row[5])
    return TrainingDataset(str(row[0]), row[1], frame, row[2], row[3], path, config)


def prediction_times(dataset: TrainingDataset) -> list[datetime]:
    return dataset.frame["prediction_timestamp"].to_list()
