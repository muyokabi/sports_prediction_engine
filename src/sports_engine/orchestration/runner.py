import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime

import duckdb

from sports_engine.core.failures import classify_failure
from sports_engine.core.telemetry import JobSummary

logger = logging.getLogger(__name__)


@contextmanager
def job_run(
    connection: duckdb.DuckDBPyConnection,
    job_name: str,
    summary: JobSummary,
    application_mode: str | None = None,
) -> Iterator[str]:
    started_at = datetime.now(UTC)
    # A process crash cannot execute the context-manager exception path. The
    # next serialized run therefore closes any same-name orphan explicitly,
    # preserving an honest audit trail instead of leaving it "running" forever.
    connection.execute(
        "UPDATE job_runs SET finished_at=?, status='failed', "
        "error_message='Recovered abandoned running job before restart', error_category='INTERRUPTED' "
        "WHERE job_name=? AND status='running'",
        [started_at, job_name],
    )
    job_run_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO job_runs (job_run_id, job_name, started_at, status, application_mode) "
        "VALUES (?, ?, ?, 'running', ?)",
        [job_run_id, job_name, started_at, application_mode],
    )

    def refresh_request_telemetry() -> None:
        """Derive logical billable calls from the durable request ledger on every exit path."""
        row = connection.execute(
            "SELECT count(*) FROM api_request_log WHERE CAST(job_run_id AS VARCHAR)=? AND endpoint<>'/status'",
            [job_run_id],
        ).fetchone()
        summary.requests_used = max(summary.requests_used, int(row[0]) if row else 0)

    try:
        yield job_run_id
    except BaseException as exc:
        refresh_request_telemetry()
        category = classify_failure(exc, job_name)
        connection.execute(
            "UPDATE job_runs SET finished_at=?, status='failed', metrics=?, error_message=?, "
            "error_category=? WHERE job_run_id=?",
            [
                datetime.now(UTC),
                json.dumps(asdict(summary)),
                str(exc),
                category.value,
                job_run_id,
            ],
        )
        logger.error("job_failed job=%s category=%s error=%s", job_name, category.value, exc)
        raise
    else:
        refresh_request_telemetry()
        connection.execute(
            "UPDATE job_runs SET finished_at=?, status='succeeded', metrics=? WHERE job_run_id=?",
            [datetime.now(UTC), json.dumps(asdict(summary)), job_run_id],
        )
