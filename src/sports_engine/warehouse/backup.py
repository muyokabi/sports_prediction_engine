import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.integrity import audit_integrity
from sports_engine.warehouse.migrations import applied_migrations, discover_migrations

COUNT_TABLES = (
    "fixtures",
    "fixture_observations",
    "fixture_quality_status",
    "odds_snapshots",
    "model_runs",
    "prediction_runs",
    "predictions",
    "prediction_decisions",
    "api_request_log",
)


@dataclass(frozen=True, slots=True)
class BackupVerification:
    valid: bool
    schema_version: int
    row_counts: dict[str, int]
    files_verified: int
    errors: tuple[str, ...]


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(project_root: Path, database_path: Path, destination: Path) -> Path:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Backup destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    connection = connect(database_path)
    try:
        connection.execute("CHECKPOINT")
        versions = applied_migrations(connection)
        counts = {}
        for table in COUNT_TABLES:
            row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
            counts[table] = int(row[0]) if row else 0
        integrity_issues = [
            {"check": issue.check, "count": issue.count, "severity": issue.severity}
            for issue in audit_integrity(connection, project_root)
        ]
    finally:
        connection.close()
    database_target = destination / "data" / "warehouse" / database_path.name
    database_target.parent.mkdir(parents=True, exist_ok=True)
    # DuckDB cannot keep its Windows file lock while shutil copies the file.
    # Hashing immediately before and after the copy makes the operation
    # fail closed if another process acquires the warehouse and changes it.
    source_digest_before = _file_digest(database_path)
    shutil.copy2(database_path, database_target)
    target_digest = _file_digest(database_target)
    source_digest_after = _file_digest(database_path)
    if source_digest_before != source_digest_after or target_digest != source_digest_before:
        raise ValueError("Warehouse changed while the backup database was being copied")
    for relative in (Path("data/raw"), Path("data/parquet"), Path("artifacts/models"), Path("config")):
        source = project_root / relative
        if source.exists():
            shutil.copytree(source, destination / relative, dirs_exist_ok=True)
    files = {
        str(path.relative_to(destination)).replace("\\", "/"): _file_digest(path)
        for path in destination.rglob("*")
        if path.is_file()
    }
    required_artifacts = [str(database_target.relative_to(destination)).replace("\\", "/")]
    config_file = destination / "config" / "app.yaml"
    if config_file.is_file():
        required_artifacts.append("config/app.yaml")
    if counts["api_request_log"]:
        required_artifacts.append("data/raw/")
    if counts["model_runs"]:
        required_artifacts.append("artifacts/models/")
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": max(versions, default=0),
        "row_counts": counts,
        "integrity_issues": integrity_issues,
        "database": str(database_target.relative_to(destination)).replace("\\", "/"),
        "files": files,
        "required_artifacts": required_artifacts,
    }
    (destination / "backup_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return destination / "backup_manifest.json"


def verify_backup(destination: Path) -> BackupVerification:
    errors: list[str] = []
    manifest_path = destination / "backup_manifest.json"
    if not manifest_path.is_file():
        return BackupVerification(False, 0, {}, 0, ("backup_manifest.json is missing",))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = 0
    for relative, expected in manifest.get("files", {}).items():
        path = destination / relative
        if not path.is_file():
            errors.append(f"missing file: {relative}")
        elif _file_digest(path) != expected:
            errors.append(f"hash mismatch: {relative}")
        else:
            verified += 1
    manifest_files = tuple(manifest.get("files", {}))
    for required in manifest.get("required_artifacts", []):
        if required.endswith("/"):
            if not any(relative.startswith(required) for relative in manifest_files):
                errors.append(f"required artifact group is missing: {required}")
        elif required not in manifest_files:
            errors.append(f"required artifact is missing: {required}")
    database_path = destination / manifest["database"]
    counts: dict[str, int] = {}
    schema_version = 0
    if database_path.is_file():
        try:
            connection = connect(database_path, read_only=True)
            versions = applied_migrations(connection)
            schema_version = max(versions, default=0)
            available = discover_migrations()
            expected_version = int(manifest["schema_version"])
            if schema_version != expected_version:
                errors.append(f"schema version mismatch: backup={schema_version}, manifest={expected_version}")
            elif schema_version > len(available):
                errors.append(
                    f"backup schema {schema_version} is newer than available migrations {len(available)}"
                )
            else:
                expected_prefix = {item.version: item.checksum for item in available[:schema_version]}
                if versions != expected_prefix:
                    errors.append("backup migration history does not match the available migration prefix")
            for table, expected in manifest["row_counts"].items():
                row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row else 0
                if counts[table] != expected:
                    errors.append(f"row count mismatch for {table}: {counts[table]} != {expected}")
            actual_issues = [
                {"check": issue.check, "count": issue.count, "severity": issue.severity}
                for issue in audit_integrity(connection, destination)
            ]
            expected_issues = manifest.get("integrity_issues", [])
            if actual_issues != expected_issues:
                errors.append(
                    "backup integrity state differs from source: "
                    f"backup={actual_issues}, source={expected_issues}"
                )
            connection.close()
        except Exception as exc:
            errors.append(f"DuckDB validation failed: {exc}")
    else:
        errors.append("backup database is missing")
    return BackupVerification(not errors, schema_version, counts, verified, tuple(errors))
