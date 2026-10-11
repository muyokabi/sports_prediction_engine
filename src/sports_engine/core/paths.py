from datetime import date, datetime
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root() / path


def dated_artifact_directory(root: Path, created_at: date | datetime) -> Path:
    """Return a stable year/month/day partition beneath an artifact category."""
    day = created_at.date() if isinstance(created_at, datetime) else created_at
    return root / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
