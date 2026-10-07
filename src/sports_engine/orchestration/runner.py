import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime

import duckdb

from sports_engine.core.telemetry import JobSummary


@contextmanager
def job_run(
    connection: duckdb.DuckDBPyConnection,
    job_name: str,
    summary: JobSummary,
    application_mode: str | None = None,
) -> Iterator[str]:
    job_run_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO job_runs (job_run_id, job_name, started_at, status, application_mode) "
        "VALUES (?, ?, ?, 'running', ?)",
        [job_run_id, job_name, datetime.now(UTC), application_mode],
    )
    try:
        yield job_run_id
    except Exception as exc:
        connection.execute(
            "UPDATE job_runs SET finished_at=?, status='failed', metrics=?, error_message=? WHERE job_run_id=?",
            [datetime.now(UTC), json.dumps(asdict(summary)), str(exc), job_run_id],
        )
        raise
    else:
        connection.execute(
            "UPDATE job_runs SET finished_at=?, status='succeeded', metrics=? WHERE job_run_id=?",
            [datetime.now(UTC), json.dumps(asdict(summary)), job_run_id],
        )
