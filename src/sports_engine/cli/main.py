import typer

from sports_engine.cli.api import app as api_app
from sports_engine.cli.data import app as data_app
from sports_engine.cli.doctor import doctor_command
from sports_engine.cli.features import app as features_app
from sports_engine.cli.football import app as football_app
from sports_engine.cli.leagues import app as leagues_app
from sports_engine.cli.models import app as models_app
from sports_engine.cli.predictions import predict_tomorrow
from sports_engine.core.logging import configure_logging

app = typer.Typer(help="Institutional football data, analytics, and prediction engine.")
app.add_typer(api_app, name="api")
app.add_typer(data_app, name="data")
app.add_typer(football_app, name="football")
app.add_typer(leagues_app, name="leagues")
app.add_typer(features_app, name="features")
app.add_typer(models_app, name="models")
app.command("doctor")(doctor_command)


@app.callback()
def callback(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    configure_logging(verbose=verbose)


@app.command("daily")
def daily() -> None:
    """Run the principal idempotent daily workflow."""
    from sports_engine.cli.football import daily as football_daily

    football_daily()


@app.command("run")
def run_analysis(
    target_date: str = typer.Option("tomorrow", "--date", help="today, tomorrow, or YYYY-MM-DD"),
    days: int = typer.Option(1, "--days", min=1, max=31, help="Bounded inclusive analysis horizon."),
    offline: bool = typer.Option(False, "--offline", help="Use persisted data without provider calls."),
) -> None:
    """Collect fresh requested-date odds, reconcile the universe, and report."""
    from sports_engine.analysis.dates import resolve_analysis_dates
    from sports_engine.analysis.service import AnalysisService
    from sports_engine.cli.runtime import open_database, provider_client
    from sports_engine.core.config import ApplicationMode, load_config
    from sports_engine.core.telemetry import JobSummary
    from sports_engine.orchestration.locks import FileLock
    from sports_engine.orchestration.runner import job_run
    from sports_engine.sports.football.ingestion.odds import OddsIngestionService
    from sports_engine.training.feedback import refresh_performance_rollups, settle_completed_predictions

    config = load_config()
    requested = resolve_analysis_dates(target_date, timezone=config.timezone, days=days)
    connection = open_database(config)
    ledger_mode = "replay" if config.mode == ApplicationMode.DEVELOPMENT else "production"
    odds_payloads = odds_snapshots = unmatched = 0
    summary = JobSummary()
    try:
        with (
            FileLock(config.state_dir / "principal-run.lock"),
            job_run(connection, "institutional.run", summary, config.mode.value) as run_id,
        ):
            if not offline and ledger_mode == "production":
                with provider_client(config, connection) as client:
                    client.get_status(purpose="institutional_run_status", job_run_id=run_id)
                    odds_service = OddsIngestionService(
                        connection,
                        client,
                        dedupe_seconds=config.odds.snapshot_dedupe_seconds,
                    )
                    for analysis_date in requested.dates:
                        fixture_count = connection.execute(
                            "SELECT count(*) FROM fixtures_current f JOIN competition_seasons cs "
                            "USING (competition_season_id) WHERE cs.ledger_mode=? AND cs.admitted "
                            "AND CAST(timezone(?, f.kickoff_utc) AS DATE)=? AND f.status_short IN ('NS','TBD')",
                            [ledger_mode, config.timezone, analysis_date],
                        ).fetchone()
                        if fixture_count and fixture_count[0]:
                            odds_result = odds_service.run(analysis_date, job_run_id=run_id)
                            odds_payloads += odds_result.payloads_seen
                            odds_snapshots += odds_result.snapshots_written
                            unmatched += odds_result.fixtures_not_in_ledger
                summary.odds_snapshots_written = odds_snapshots
            settlement = settle_completed_predictions(connection)
            refresh_performance_rollups(connection)
            result = AnalysisService(connection, config.artifacts_dir / "reports").run(
                requested.start,
                requested.end,
                timezone=config.timezone,
                ledger_mode=ledger_mode,
                job_run_id=run_id,
            )
    finally:
        connection.close()
    typer.echo(
        f"Analysis {result.analysis_run_id}: {result.state}; expected={result.expected_fixtures}; "
        f"terminal={result.terminal_fixtures}; odds_payloads={odds_payloads}; "
        f"odds_snapshots={odds_snapshots}; unmatched_odds_fixtures={unmatched}; report={result.report_path}"
        f"; settled_predictions={settlement.predictions_settled}"
    )


@app.command("train")
def train(
    model: str = typer.Option(..., help="Model type to train."),
    dataset: str | None = typer.Option(None, help="Feature dataset ID or name; latest when omitted."),
    calibration: str | None = typer.Option(None, help="Optional platt or isotonic calibration."),
    mode: str = typer.Option("full_refit", help="full_refit or warm_start candidate generation."),
    parent: str | None = typer.Option(None, help="Immutable parent version for warm_start."),
) -> None:
    from sports_engine.cli.runtime import open_database
    from sports_engine.core.config import load_config
    from sports_engine.training.trainer import ModelTrainer

    config = load_config()
    connection = open_database(config)
    try:
        result = ModelTrainer(
            connection,
            config.artifacts_dir,
            random_seed=config.models.random_seed,
            cpu_threads=config.models.cpu_threads,
            time_decay_half_life_days=config.models.time_decay_half_life_days,
        ).train(
            model,
            dataset_name=dataset,
            calibration_method=calibration,
            training_mode=mode,
            parent_model_version=parent,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    finally:
        connection.close()
    typer.echo(
        f"Registered candidate {result.version} from dataset {result.dataset_id}; "
        f"test log-loss={result.metrics['log_loss']:.6f}; artifact={result.artifact_path}"
    )


@app.command("evaluate")
def evaluate(
    model: str | None = typer.Option(None, help="Model type to evaluate."),
    all_models: bool = typer.Option(False, "--all"),
    dataset: str | None = typer.Option(None, help="Feature dataset ID or name; latest when omitted."),
    rolling_periods: int | None = typer.Option(None, min=1, help="Use a rolling training window."),
) -> None:
    from sports_engine.cli.runtime import open_database
    from sports_engine.core.config import load_config
    from sports_engine.evaluation.reports import WalkForwardEvaluator
    from sports_engine.models.registry import MODEL_TYPES

    if not all_models and model is None:
        typer.echo("Specify --model or --all.", err=True)
        raise typer.Exit(2)
    config = load_config()
    connection = open_database(config)
    evaluator = WalkForwardEvaluator(
        connection,
        config.artifacts_dir / "evaluation",
        random_seed=config.models.random_seed,
        cpu_threads=config.models.cpu_threads,
        time_decay_half_life_days=config.models.time_decay_half_life_days,
    )
    try:
        for model_type in MODEL_TYPES if all_models else (model,):
            assert model_type is not None
            report = evaluator.evaluate(model_type, dataset_name=dataset, rolling_train_periods=rolling_periods)
            typer.echo(
                f"{model_type}: folds={len(report.fold_metrics)} "
                f"log-loss={report.aggregate_metrics['log_loss']:.6f} report={report.path}"
            )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    finally:
        connection.close()


@app.command("backtest")
def backtest(all_models: bool = typer.Option(False, "--all")) -> None:
    from sports_engine.cli.runtime import open_database
    from sports_engine.core.config import load_config
    from sports_engine.evaluation.backtest import BacktestService

    config = load_config()
    connection = open_database(config)
    try:
        result = BacktestService(connection, config.artifacts_dir / "backtests").run(all_models=all_models)
    finally:
        connection.close()
    typer.echo(
        f"Backtest: predictions={result.predictions_seen} decisions={result.decisions_written} "
        f"bets={result.bets} profit={result.profit:.3f} "
        f"roi={result.roi if result.roi is not None else 'n/a'} report={result.report_path}"
    )


prediction_app = typer.Typer(help="Generate and inspect persisted predictions.")
prediction_app.command("tomorrow")(predict_tomorrow)
app.add_typer(prediction_app, name="predict")


if __name__ == "__main__":
    app()
