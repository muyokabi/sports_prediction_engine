import typer
from rich.console import Console
from rich.table import Table

from sports_engine.cli.runtime import open_database, provider_client
from sports_engine.core.config import load_config
from sports_engine.sports.football.ingestion.discovery import (
    CompetitionDiscoveryService,
    admit_observation_universe,
)

app = typer.Typer(help="Discover and govern API-Football competition universes.")
console = Console()


@app.command("discover")
def discover() -> None:
    """Discover all current seasons in one catalog request and score suitability."""
    config = load_config()
    connection = open_database(config)
    try:
        with provider_client(config, connection) as client:
            client.get_status(purpose="competition_discovery_status")
            result = CompetitionDiscoveryService(connection, client).run()
    finally:
        connection.close()
    console.print(
        f"Discovered {result.discovered} current competitions: "
        f"observation={result.observation}, rejected={result.rejected}, "
        f"other_discovered={result.discovered - result.observation - result.rejected}."
    )


@app.command("list")
def list_competitions(limit: int = typer.Option(50, min=1, max=500)) -> None:
    config = load_config()
    connection = open_database(config)
    rows = connection.execute(
        "SELECT provider_competition_id, name, country, provider_season, universe_state, "
        "data_quality_score, market_quality_score, suitability_score FROM competition_discoveries "
        "ORDER BY suitability_score DESC, name LIMIT ?",
        [limit],
    ).fetchall()
    connection.close()
    table = Table("ID", "Competition", "Country", "Season", "Universe", "Data", "Market", "Suitability")
    for row in rows:
        table.add_row(*(str(value) for value in row))
    console.print(table)


@app.command("admit-observation")
def admit_observation(limit: int = typer.Option(40, min=1, max=200)) -> None:
    """Admit scored candidates for collection, without declaring them actionable."""
    config = load_config()
    connection = open_database(config)
    try:
        admitted = admit_observation_universe(connection, limit=limit)
    finally:
        connection.close()
    console.print(f"Admitted {len(admitted)} competition-seasons to the observation collection universe.")
