import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from sports_engine.core.cleanup import cleanup_generated_files
from sports_engine.core.config import load_config
from sports_engine.core.paths import project_root
from sports_engine.warehouse.backup import create_backup, verify_backup
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.integrity import audit_integrity
from sports_engine.warehouse.migrations import migrate

app = typer.Typer(help="Warehouse lifecycle commands.")
console = Console()


@app.command("migrate")
def migrate_command() -> None:
    config = load_config()
    connection = connect(config.database_path)
    applied = migrate(connection)
    connection.close()
    console.print(f"Applied migrations: {applied or 'none (current)'}")


@app.command("integrity")
def integrity() -> None:
    config = load_config()
    connection = connect(config.database_path)
    migrate(connection)
    issues = audit_integrity(connection)
    connection.close()
    if not issues:
        console.print("[green]Database integrity audit passed.[/]")
        return
    table = Table("Severity", "Check", "Count")
    for issue in issues:
        table.add_row(issue.severity, issue.check, str(issue.count))
    console.print(table)
    raise typer.Exit(1)


@app.command("cleanup")
def cleanup_command(
    apply: bool = typer.Option(False, "--apply", help="Delete eligible generated files; default is dry-run."),
    older_than_days: int | None = typer.Option(
        None,
        "--older-than-days",
        min=0,
        max=365,
        help="Override cleanup.retention_days for this invocation.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Inspect or remove expired, regenerable development and test artifacts."""
    config = load_config()
    result = cleanup_generated_files(config, retention_days=older_than_days, apply=apply)
    payload = {
        "mode": "apply" if apply else "dry-run",
        "eligible": [
            {
                "path": str(candidate.path),
                "bytes": candidate.bytes,
                "newest_modified_at": candidate.newest_modified_at.isoformat(),
            }
            for candidate in result.candidates
        ],
        "removed": [str(path) for path in result.removed],
        "bytes_removed": result.bytes_removed,
        "errors": list(result.errors),
    }
    if as_json:
        console.print_json(json.dumps(payload))
    else:
        action = "Removed" if apply else "Would remove"
        console.print(
            f"{action} {len(result.removed) if apply else len(result.candidates)} generated targets "
            f"({result.bytes_removed if apply else sum(item.bytes for item in result.candidates):,} bytes)."
        )
        for candidate in result.candidates:
            console.print(f"- {candidate.path} ({candidate.bytes:,} bytes)")
        for error in result.errors:
            console.print(f"[red]{error}[/]")
    if result.errors:
        raise typer.Exit(1)


@app.command("backup")
def backup(destination: Path) -> None:
    config = load_config()
    try:
        manifest = create_backup(project_root(), config.database_path, destination.resolve())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Backup failed: {exc}[/]")
        raise typer.Exit(1) from exc
    console.print(f"Backup created: {manifest}")


@app.command("verify-backup")
def verify_backup_command(destination: Path) -> None:
    result = verify_backup(destination.resolve())
    if not result.valid:
        for error in result.errors:
            console.print(f"[red]{error}[/]")
        raise typer.Exit(1)
    console.print(
        f"Backup verified: schema={result.schema_version} files={result.files_verified} tables={len(result.row_counts)}"
    )
