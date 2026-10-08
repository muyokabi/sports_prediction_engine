from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

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
