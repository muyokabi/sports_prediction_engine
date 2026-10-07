import json
from datetime import UTC, datetime
from typing import Any

import duckdb


def put(connection: duckdb.DuckDBPyConnection, key: str, value: Any, job_run_id: str | None) -> None:
    connection.execute(
        "INSERT INTO checkpoints VALUES (?, ?, ?, ?) "
        "ON CONFLICT (checkpoint_key) DO UPDATE SET value=excluded.value, "
        "updated_at=excluded.updated_at, job_run_id=excluded.job_run_id",
        [key, json.dumps(value), datetime.now(UTC), job_run_id],
    )


def get(connection: duckdb.DuckDBPyConnection, key: str) -> Any | None:
    row = connection.execute("SELECT value FROM checkpoints WHERE checkpoint_key=?", [key]).fetchone()
    return json.loads(row[0]) if row else None
