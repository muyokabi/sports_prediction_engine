import uuid
from pathlib import Path

import pytest

from sports_engine.core.telemetry import JobSummary
from sports_engine.orchestration.runner import job_run
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def test_job_run_persists_success_metrics(tmp_path: Path) -> None:
    connection = connect(tmp_path / "jobs.duckdb")
    migrate(connection)
    summary = JobSummary(fixtures_discovered=3)
    with job_run(connection, "test.success", summary) as identifier:
        summary.fixtures_updated = 2
    row = connection.execute(
        "SELECT status, metrics->>'fixtures_discovered', metrics->>'fixtures_updated' FROM job_runs WHERE job_run_id=?",
        [identifier],
    ).fetchone()
    assert row == ("succeeded", "3", "2")
    connection.close()


def test_job_run_persists_failure_and_reraises(tmp_path: Path) -> None:
    connection = connect(tmp_path / "jobs.duckdb")
    migrate(connection)
    with pytest.raises(RuntimeError, match="broken"), job_run(connection, "test.failure", JobSummary()):
        raise RuntimeError("broken")
    row = connection.execute(
        "SELECT status, error_message, error_category FROM job_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    assert row == ("failed", "broken", "UNCLASSIFIED_FAILURE")
    connection.close()


def test_job_run_derives_request_count_even_when_job_fails(tmp_path: Path) -> None:
    connection = connect(tmp_path / "failed-request-telemetry.duckdb")
    migrate(connection)
    summary = JobSummary()
    with (
        pytest.raises(RuntimeError, match="network lost"),
        job_run(connection, "test.provider-failure", summary) as identifier,
    ):
        connection.execute(
            "INSERT INTO api_request_log "
            "(request_id, provider, endpoint, query_hash, started_at, purpose, priority, job_run_id) "
            "VALUES (?, 'test', '/fixtures', 'hash', current_timestamp, 'test', 'P1', ?)",
            [uuid.uuid4(), identifier],
        )
        connection.execute(
            "INSERT INTO api_request_log "
            "(request_id, provider, endpoint, query_hash, started_at, purpose, priority, job_run_id) "
            "VALUES (?, 'test', '/status', 'hash', current_timestamp, 'test', 'P0', ?)",
            [uuid.uuid4(), identifier],
        )
        raise RuntimeError("network lost")
    assert connection.execute(
        "SELECT metrics->>'requests_used' FROM job_runs WHERE job_run_id=?", [identifier]
    ).fetchone() == ("1",)
    connection.close()


def test_job_run_records_keyboard_interrupt_and_recovers_orphan(tmp_path: Path) -> None:
    connection = connect(tmp_path / "jobs.duckdb")
    migrate(connection)
    connection.execute(
        "INSERT INTO job_runs (job_run_id, job_name, started_at, status) "
        "VALUES ('00000000-0000-0000-0000-000000000001', 'test.interrupt', current_timestamp, 'running')"
    )
    with pytest.raises(KeyboardInterrupt), job_run(connection, "test.interrupt", JobSummary()):
        raise KeyboardInterrupt
    rows = connection.execute(
        "SELECT status, error_message, error_category FROM job_runs WHERE job_name='test.interrupt' ORDER BY started_at"
    ).fetchall()
    assert rows == [
        ("failed", "Recovered abandoned running job before restart", "INTERRUPTED"),
        ("failed", "", "INTERRUPTED"),
    ]
    connection.close()
