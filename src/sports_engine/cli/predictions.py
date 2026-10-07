from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table

from sports_engine.cli.runtime import open_database
from sports_engine.core.config import ApplicationMode, load_config

console = Console()


def predict_tomorrow(
    target_date: str | None = typer.Option(None, "--date", help="Override the prediction date."),
) -> None:
    from sports_engine.sports.football.prediction.service import PredictionService

    config = load_config()
    connection = open_database(config)
    requested = (
        date.fromisoformat(target_date)
        if target_date
        else datetime.now(ZoneInfo(config.timezone)).date() + timedelta(days=1)
    )
    ledger_mode = "replay" if config.mode == ApplicationMode.DEVELOPMENT else "production"
    service = PredictionService(
        connection,
        windows=config.features.windows,
        exponential_half_life=config.features.exponential_half_life,
        prediction_lead_hours=config.features.prediction_lead_hours,
    )
    try:
        result = service.predict(requested, ledger_mode=ledger_mode, timezone=config.timezone)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc
    finally:
        connection.close()
    table = Table(
        "Kickoff",
        "Competition",
        "Fixture",
        "Model H/D/A",
        "Market H/D/A",
        "Difference H/D/A",
        "Quality",
        "Model version",
        "Odds observed",
    )
    for row in result.frame.iter_rows(named=True):
        table.add_row(
            str(row["kickoff_utc"]),
            str(row["competition"]),
            f"{row['home_team_name']} v {row['away_team_name']}",
            f"{row['probability_home']:.3f}/{row['probability_draw']:.3f}/{row['probability_away']:.3f}",
            (
                f"{row.get('bookmaker_home_fair'):.3f}/"
                f"{row.get('bookmaker_draw_fair'):.3f}/"
                f"{row.get('bookmaker_away_fair'):.3f}"
                if all(
                    row.get(name) is not None
                    for name in (
                        "bookmaker_home_fair",
                        "bookmaker_draw_fair",
                        "bookmaker_away_fair",
                    )
                )
                else "unavailable"
            ),
            (
                f"{row.get('probability_difference_home'):.3f}/"
                f"{row.get('probability_difference_draw'):.3f}/"
                f"{row.get('probability_difference_away'):.3f}"
                if all(
                    row.get(name) is not None
                    for name in (
                        "probability_difference_home",
                        "probability_difference_draw",
                        "probability_difference_away",
                    )
                )
                else "unavailable"
            ),
            str(row["data_quality_status"]),
            str(row["model_version"]),
            str(row["odds_snapshot_timestamp"] or "unavailable"),
        )
    console.print(
        f"Prediction run {result.prediction_run_id} using {result.model_version} for {result.fixture_count} fixtures."
    )
    console.print(table)
