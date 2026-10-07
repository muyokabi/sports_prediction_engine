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
    row = connection.execute("SELECT status, error_message FROM job_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    assert row == ("failed", "broken")
    connection.close()
