from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sports_engine.core.config import AppConfig
from sports_engine.core.paths import project_root


@dataclass(frozen=True)
class CleanupCandidate:
    path: Path
    bytes: int
    newest_modified_at: datetime


@dataclass(frozen=True)
class CleanupResult:
    ran: bool
    candidates: tuple[CleanupCandidate, ...]
    removed: tuple[Path, ...]
    bytes_removed: int
    errors: tuple[str, ...]
    reason: str | None = None


def _tree_stats(path: Path) -> tuple[int, datetime]:
    if path.is_file():
        stat = path.stat()
        return stat.st_size, datetime.fromtimestamp(stat.st_mtime, UTC)
    total = 0
    newest = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    for item in path.rglob("*"):
        if item.is_file():
            stat = item.stat()
            total += stat.st_size
            newest = max(newest, datetime.fromtimestamp(stat.st_mtime, UTC))
    return total, newest


def _safe_candidate(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    resolved.relative_to(resolved_root)
    if resolved == resolved_root:
        raise ValueError("cleanup target cannot be the project root")
    return resolved


def _candidate_paths(root: Path, config: AppConfig) -> set[Path]:
    paths: set[Path] = set()
    exact = (
        root / ".pytest_cache",
        root / ".mypy_cache",
        root / ".ruff_cache",
        root / ".coverage",
        root / "htmlcov",
        config.artifacts_dir / "test-tmp",
        config.artifacts_dir / "build-final",
    )
    paths.update(path for path in exact if path.exists())
    for parent in (root / ".tmp", config.state_dir):
        if parent.is_dir():
            paths.update(path for path in parent.glob("pytest-*") if path.exists())
    for parent in (root / "src", root / "tests"):
        if parent.is_dir():
            paths.update(path for path in parent.rglob("__pycache__") if path.is_dir())
    return paths


def cleanup_generated_files(
    config: AppConfig,
    *,
    retention_days: int | None = None,
    apply: bool = False,
    now: datetime | None = None,
    root: Path | None = None,
) -> CleanupResult:
    cleanup_root = (root or project_root()).resolve()
    observed = now or datetime.now(UTC)
    days = config.cleanup.retention_days if retention_days is None else retention_days
    if days < 0:
        raise ValueError("retention_days must be non-negative")
    cutoff = observed - timedelta(days=days)
    candidates: list[CleanupCandidate] = []
    errors: list[str] = []
    for raw_path in sorted(_candidate_paths(cleanup_root, config), key=lambda item: str(item)):
        try:
            path = _safe_candidate(cleanup_root, raw_path)
            size, newest = _tree_stats(path)
            if newest <= cutoff:
                candidates.append(CleanupCandidate(path, size, newest))
        except (OSError, ValueError) as exc:
            errors.append(f"{raw_path}: {exc}")

    removed: list[Path] = []
    bytes_removed = 0
    if apply:
        for candidate in candidates:
            try:
                if candidate.path.is_dir():
                    shutil.rmtree(candidate.path)
                else:
                    candidate.path.unlink(missing_ok=True)
                removed.append(candidate.path)
                bytes_removed += candidate.bytes
            except OSError as exc:
                errors.append(f"{candidate.path}: {exc}")
    return CleanupResult(True, tuple(candidates), tuple(removed), bytes_removed, tuple(errors))


def run_scheduled_cleanup(config: AppConfig, *, now: datetime | None = None) -> CleanupResult:
    if not config.cleanup.enabled:
        return CleanupResult(False, (), (), 0, (), "disabled")
    observed = now or datetime.now(UTC)
    marker = config.state_dir / "generated-cleanup.json"
    if marker.is_file():
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            previous = datetime.fromisoformat(str(payload["completed_at"]))
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=UTC)
            if observed - previous < timedelta(hours=config.cleanup.interval_hours):
                return CleanupResult(False, (), (), 0, (), "not_due")
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            pass
    result = cleanup_generated_files(config, apply=True, now=observed)
    if result.errors:
        return result
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "completed_at": observed.isoformat(),
                    "retention_days": config.cleanup.retention_days,
                    "removed": len(result.removed),
                    "bytes_removed": result.bytes_removed,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        return CleanupResult(
            result.ran,
            result.candidates,
            result.removed,
            result.bytes_removed,
            (f"{marker}: {exc}",),
        )
    return result
