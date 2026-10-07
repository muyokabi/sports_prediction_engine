import json

import typer
from rich.console import Console
from rich.table import Table

from sports_engine.cli.runtime import open_database
from sports_engine.core.config import load_config
from sports_engine.models.registry import ModelRegistry

app = typer.Typer(help="Inspect model artifacts and promotion state.")
console = Console()


@app.command("list")
def list_models(as_json: bool = typer.Option(False, "--json")) -> None:
    config = load_config()
    connection = open_database(config)
    rows = connection.execute(
        "SELECT model_type, version, status, created_at, artifact_path FROM model_runs ORDER BY created_at DESC"
    ).fetchall()
    connection.close()
    if as_json:
        console.print_json(
            json.dumps(
                [
                    dict(
                        zip(
                            ("model_type", "version", "status", "created_at", "artifact_path"),
                            row,
                            strict=True,
                        )
                    )
                    for row in rows
                ],
                default=str,
            )
        )
        return
    table = Table("Type", "Version", "Status", "Created", "Artifact")
    for row in rows:
        table.add_row(*(str(value) for value in row))
    console.print(table)


@app.command("leaderboard")
def leaderboard() -> None:
    config = load_config()
    connection = open_database(config)
    rows = connection.execute(
        "SELECT model_type, version, status, metrics FROM model_runs ORDER BY created_at DESC"
    ).fetchall()
    connection.close()
    table = Table("Type", "Version", "Status", "Metrics")
    for row in rows:
        table.add_row(*(str(value) for value in row))
    console.print(table)


@app.command("promote")
def promote(version: str = typer.Argument(..., help="Candidate model version.")) -> None:
    config = load_config()
    connection = open_database(config)
    try:
        ModelRegistry(connection).promote(version)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc
    finally:
        connection.close()
    console.print(f"Promoted [bold]{version}[/] to champion.")


@app.command("reject")
def reject(version: str = typer.Argument(..., help="Candidate model version.")) -> None:
    config = load_config()
    connection = open_database(config)
    try:
        ModelRegistry(connection).reject(version)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc
    finally:
        connection.close()
    console.print(f"Rejected candidate [bold]{version}[/].")
