import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sports_engine.core.cleanup import cleanup_generated_files, run_scheduled_cleanup
from sports_engine.core.config import AppConfig, CleanupConfig


def _config(root: Path, *, retention_days: int = 7) -> AppConfig:
    return AppConfig(
        data_dir=root / "data",
        artifacts_dir=root / "artifacts",
        state_dir=root / "state",
        logs_dir=root / "logs",
        database_path=root / "data" / "warehouse" / "sports.duckdb",
        cleanup=CleanupConfig(retention_days=retention_days),
    )


def test_cleanup_is_dry_run_by_default_and_never_targets_audit_artifacts(tmp_path: Path) -> None:
    config = _config(tmp_path)
    generated = tmp_path / "state" / "pytest-old"
    generated.mkdir(parents=True)
    (generated / "test.duckdb").write_bytes(b"temporary")
    protected = tmp_path / "artifacts" / "models" / "model.pkl"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"immutable")
    now = datetime.now(UTC) + timedelta(days=8)

    result = cleanup_generated_files(config, now=now, root=tmp_path)

    assert [item.path for item in result.candidates] == [generated.resolve()]
    assert result.removed == ()
    assert generated.exists()
    assert protected.exists()


def test_cleanup_apply_removes_only_expired_allowlisted_targets(tmp_path: Path) -> None:
    config = _config(tmp_path)
    old = tmp_path / ".tmp" / "pytest-old"
    recent = tmp_path / ".tmp" / "pytest-recent"
    old.mkdir(parents=True)
    recent.mkdir(parents=True)
    (old / "old.bin").write_bytes(b"old")
    (recent / "recent.bin").write_bytes(b"recent")
    observed = datetime.now(UTC)
    old_timestamp = (observed - timedelta(days=8)).timestamp()
    for path in (old / "old.bin", old):
        os.utime(path, (old_timestamp, old_timestamp))

    result = cleanup_generated_files(config, apply=True, now=observed, root=tmp_path)

    assert result.errors == ()
    assert result.removed == (old.resolve(),)
    assert not old.exists()
    assert recent.exists()


def test_scheduled_cleanup_records_completion_and_respects_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, retention_days=0)
    generated = config.state_dir / "pytest-expired"
    generated.mkdir(parents=True)
    (generated / "test.duckdb").write_bytes(b"temporary")
    observed = datetime.now(UTC) + timedelta(seconds=1)
    monkeypatch.setattr("sports_engine.core.cleanup.project_root", lambda: tmp_path)

    first = run_scheduled_cleanup(config, now=observed)
    second = run_scheduled_cleanup(config, now=observed + timedelta(hours=1))

    assert first.ran
    assert first.removed == (generated.resolve(),)
    assert (config.state_dir / "generated-cleanup.json").is_file()
    assert not second.ran
    assert second.reason == "not_due"
