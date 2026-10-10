import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import (
    NoEligibleModelError,
    ProviderAuthenticationError,
    ProviderPlanAccessError,
    ProviderRateLimitError,
    QuotaExhaustedError,
)
from sports_engine.core.failures import FailureCategory, classify_failure
from sports_engine.orchestration.locks import FileLock
from sports_engine.sports.football.ingestion.daily_update import DailyUpdateService
from sports_engine.sports.football.quality.report import quality_summary
from sports_engine.warehouse.backup import create_backup, verify_backup
from sports_engine.warehouse.checkpoints import get as get_checkpoint
from sports_engine.warehouse.checkpoints import put as put_checkpoint
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.integrity import audit_integrity
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.leagues import upsert_competition_season
from sports_engine.warehouse.transactions import transaction


class DateProvider:
    def __init__(self, fail_on: date | None = None) -> None:
        self.dates: list[date] = []
        self.fail_on = fail_on

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        requested = date.fromisoformat(str(parameters["date"]))
        self.dates.append(requested)
        if requested == self.fail_on:
            raise RuntimeError("simulated provider interruption")
        return []


@pytest.mark.parametrize("downtime_days", [2, 3, 7])
def test_daily_catch_up_discovers_every_missed_date(tmp_path: Path, downtime_days: int) -> None:
    connection = connect(tmp_path / f"catch-up-{downtime_days}.duckdb")
    migrate(connection)
    operational = date(2026, 10, 7)
    put_checkpoint(
        connection,
        "daily_discovery:replay",
        {"last_date": date.fromordinal(operational.toordinal() - downtime_days).isoformat()},
        None,
    )
    provider = DateProvider()
    result = DailyUpdateService(
        connection,
        provider,
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run_catch_up(operational, ledger_mode="replay")
    assert provider.dates == [
        date.fromordinal(operational.toordinal() - downtime_days + offset) for offset in range(1, downtime_days + 2)
    ]
    assert result.discovery_dates == tuple(provider.dates)
    assert get_checkpoint(connection, "daily_discovery:replay") == {
        "last_date": date.fromordinal(operational.toordinal() + 1).isoformat()
    }
    connection.close()


def test_daily_catch_up_resumes_after_failure_without_losing_progress(tmp_path: Path) -> None:
    connection = connect(tmp_path / "resume.duckdb")
    migrate(connection)
    operational = date(2026, 10, 7)
    put_checkpoint(connection, "daily_discovery:replay", {"last_date": "2026-10-04"}, None)
    failing = DateProvider(date(2026, 10, 6))
    service = DailyUpdateService(
        connection,
        failing,
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    )
    with pytest.raises(RuntimeError, match="interruption"):
        service.run_catch_up(operational, ledger_mode="replay")
    assert get_checkpoint(connection, "daily_discovery:replay") == {"last_date": "2026-10-05"}
    resumed = DateProvider()
    service = DailyUpdateService(
        connection,
        resumed,
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    )
    service.run_catch_up(operational, ledger_mode="replay")
    assert resumed.dates == [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
    connection.close()


def test_normalization_failure_preserves_existing_raw_evidence(tmp_path: Path) -> None:
    connection = connect(tmp_path / "normalization-crash.duckdb")
    migrate(connection)
    upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="test",
        priority=1,
    )
    raw_path = tmp_path / "raw-before-normalization.json.gz"
    raw_path.write_bytes(b"preserved")

    class InvalidProvider:
        def get(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "fixture": {"id": 1, "date": "2024-05-01T12:00:00Z", "status": {"short": "FT"}},
                    "league": {"id": 39, "season": 2024},
                    "teams": {},
                }
            ]

    service = DailyUpdateService(
        connection,
        InvalidProvider(),
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: str(raw_path),
    )
    with pytest.raises(KeyError):
        service.run(date(2024, 5, 1), ledger_mode="replay", discovery_dates=[date(2024, 5, 1)])
    assert raw_path.read_bytes() == b"preserved"
    assert connection.execute("SELECT count(*) FROM fixtures").fetchone() == (0,)
    connection.close()


def test_quality_integrity_and_backup_verification(tmp_path: Path) -> None:
    project = tmp_path / "project"
    database_path = project / "data" / "warehouse" / "sports.duckdb"
    connection = connect(database_path)
    migrate(connection)
    upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="test",
        priority=1,
    )
    assert quality_summary(connection)[0].total == 0
    assert audit_integrity(connection) == []
    connection.close()
    (project / "config").mkdir(parents=True)
    (project / "config" / "app.yaml").write_text("mode: development\n", encoding="utf-8")
    destination = tmp_path / "backup"
    manifest = create_backup(project, database_path, destination)
    assert json.loads(manifest.read_text())["schema_version"] == 33
    verified = verify_backup(destination)
    assert verified.valid
    assert verified.row_counts["fixtures"] == 0
    (destination / "config" / "app.yaml").write_text("tampered\n", encoding="utf-8")
    assert not verify_backup(destination).valid


def test_database_transaction_rolls_back_after_interruption(tmp_path: Path) -> None:
    connection = connect(tmp_path / "rollback.duckdb")
    migrate(connection)
    with pytest.raises(RuntimeError, match="crash"), transaction(connection):
        connection.execute(
            "INSERT INTO checkpoints (checkpoint_key, value, updated_at, job_run_id) "
            "VALUES ('crash-test', '{}', current_timestamp, NULL)"
        )
        raise RuntimeError("simulated crash")
    assert connection.execute("SELECT count(*) FROM checkpoints WHERE checkpoint_key='crash-test'").fetchone() == (0,)
    connection.close()


def test_file_lock_rejects_overlapping_job_and_recovers(tmp_path: Path) -> None:
    lock_path = tmp_path / "daily.lock"
    with FileLock(lock_path), pytest.raises(RuntimeError, match="already held"), FileLock(lock_path):
        pass
    with FileLock(lock_path):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_file_lock_recovers_when_recorded_process_no_longer_exists(tmp_path: Path) -> None:
    lock_path = tmp_path / "daily.lock"
    lock_path.write_text("2147483647", encoding="ascii")
    with FileLock(lock_path):
        assert int(lock_path.read_text(encoding="ascii")) > 0
    assert not lock_path.exists()


@pytest.mark.parametrize(
    ("error", "job_name", "expected"),
    [
        (ProviderAuthenticationError(), "daily", FailureCategory.AUTHENTICATION_FAILURE),
        (ProviderRateLimitError(), "daily", FailureCategory.QUOTA_EXHAUSTION),
        (QuotaExhaustedError(), "daily", FailureCategory.QUOTA_EXHAUSTION),
        (ProviderPlanAccessError(), "daily", FailureCategory.PLAN_RESTRICTION),
        (NoEligibleModelError(), "predict.tomorrow", FailureCategory.NO_ELIGIBLE_MODEL),
        (RuntimeError(), "football.odds", FailureCategory.ODDS_INGESTION_FAILURE),
        (RuntimeError(), "predict.tomorrow", FailureCategory.PREDICTION_FAILURE),
        (RuntimeError(), "data.backup", FailureCategory.BACKUP_FAILURE),
    ],
)
def test_failure_categories_are_actionable(error: Exception, job_name: str, expected: FailureCategory) -> None:
    assert classify_failure(error, job_name) == expected
