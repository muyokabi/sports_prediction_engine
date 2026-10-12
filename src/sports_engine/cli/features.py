import json

import typer
from rich.console import Console

from sports_engine.cli.runtime import open_database
from sports_engine.core.config import ApplicationMode, load_config
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder

app = typer.Typer(help="Point-in-time feature dataset workflows.")
console = Console()


@app.command("build")
def build(
    name: str = typer.Option("football-training"),
    as_json: bool = typer.Option(False, "--json"),
    include_observation_leagues: bool = typer.Option(
        False,
        "--include-observation-leagues",
        help=(
            "Include discovery observation leagues in a research dataset; "
            "production training uses ACTIONABLE leagues."
        ),
    ),
) -> None:
    config = load_config()
    ledger_mode = "replay" if config.mode == ApplicationMode.DEVELOPMENT else "production"
    connection = open_database(config)
    try:
        artifact = PointInTimeFeatureBuilder(
            connection,
            config.data_dir / "parquet" / "features",
            windows=config.features.windows,
            exponential_half_life=config.features.exponential_half_life,
            prediction_lead_hours=config.features.prediction_lead_hours,
            historical_ledger_modes=config.models.historical_training_ledgers,
            replay_universe_states=None if include_observation_leagues else ["ACTIONABLE"],
        ).build(name, ledger_mode=ledger_mode)
    except ValueError as exc:
        connection.close()
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc
    connection.close()
    payload = {
        "dataset_id": artifact.dataset_id,
        "rows": artifact.row_count,
        "parquet_path": str(artifact.parquet_path),
        "schema_hash": artifact.schema_hash,
        "dataset_hash": artifact.dataset_hash,
    }
    if as_json:
        console.print_json(json.dumps(payload))
    else:
        console.print(
            f"Feature dataset {artifact.dataset_id}: rows={artifact.row_count} "
            f"schema={artifact.schema_hash[:12]} data={artifact.dataset_hash[:12]} "
            f"path={artifact.parquet_path}"
        )
