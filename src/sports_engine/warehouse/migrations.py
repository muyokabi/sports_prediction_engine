import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from sports_engine.core.paths import project_root

MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str


def discover_migrations(directory: Path | None = None) -> list[Migration]:
    root = directory or project_root() / "migrations"
    migrations: list[Migration] = []
    for path in sorted(root.glob("*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            continue
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        migrations.append(Migration(int(match["version"]), match["name"], path, checksum))
    versions = [item.version for item in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise ValueError(f"Migrations must be contiguous from 001; found {versions}")
    return migrations


def _schema_versions_exists(connection: duckdb.DuckDBPyConnection) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name='schema_versions'"
    ).fetchone()
    return bool(row and row[0])


def applied_migrations(connection: duckdb.DuckDBPyConnection) -> dict[int, str]:
    if not _schema_versions_exists(connection):
        return {}
    return dict(connection.execute("SELECT version, checksum FROM schema_versions").fetchall())


def migrate(connection: duckdb.DuckDBPyConnection, directory: Path | None = None) -> list[int]:
    migrations = discover_migrations(directory)
    applied = applied_migrations(connection)
    completed: list[int] = []
    for migration in migrations:
        if migration.version in applied:
            if applied[migration.version] != migration.checksum:
                raise RuntimeError(f"Applied migration {migration.version:03d} checksum changed")
            continue
        connection.begin()
        try:
            connection.execute(migration.path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_versions VALUES (?, ?, ?, ?)",
                [migration.version, migration.name, migration.checksum, datetime.now(UTC)],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        completed.append(migration.version)
    return completed


def pending_migrations(connection: duckdb.DuckDBPyConnection) -> list[Migration]:
    applied = applied_migrations(connection)
    return [migration for migration in discover_migrations() if migration.version not in applied]
