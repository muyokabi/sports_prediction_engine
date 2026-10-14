from pathlib import Path

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

    # Call the command implementation directly with a real value rather than
    # Typer's OptionInfo default.
    football_daily(as_of=None)


@app.command("run")
def run_analysis(
    target_date: str = typer.Option("tomorrow", "--date", help="today, tomorrow, or YYYY-MM-DD"),
    days: int = typer.Option(1, "--days", min=1, max=31, help="Bounded inclusive analysis horizon."),
    offline: bool = typer.Option(False, "--offline", help="Use persisted data without provider calls."),
) -> None:
    """Collect fresh requested-date odds, reconcile the universe, and report."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from sports_engine.analysis.dates import resolve_analysis_dates
    from sports_engine.analysis.service import AnalysisService
    from sports_engine.cli.runtime import open_database, provider_client
    from sports_engine.core.config import ApplicationMode, load_config
    from sports_engine.core.telemetry import JobSummary
    from sports_engine.markets.odds_age_research import refresh_odds_age_research
    from sports_engine.orchestration.locks import FileLock
    from sports_engine.orchestration.runner import job_run
    from sports_engine.sports.football.ingestion.odds import OddsIngestionService
    from sports_engine.training.feedback import (
        refresh_performance_rollups,
        settle_completed_predictions,
        settle_shadow_opportunities,
    )
    from sports_engine.warehouse.integrity import audit_integrity

    config = load_config()
    requested = resolve_analysis_dates(target_date, timezone=config.timezone, days=days)
    learning = None
    daily_odds_date = None
    if not offline:
        from sports_engine.cli.doctor import run_doctor
        from sports_engine.cli.football import daily as football_daily

        if not run_doctor(connectivity=False, verify_current_season=False):
            raise typer.Exit(2)
        # The principal command owns routine catch-up, enrichment, repair,
        # surplus backfill, settlement, feature feedback, and prediction work.
        learning = football_daily(as_of=None)
        daily_odds_date = datetime.now(ZoneInfo(config.timezone)).date() + timedelta(days=config.odds.target_days_ahead)
    connection = open_database(config)
    ledger_mode = "replay" if config.mode == ApplicationMode.DEVELOPMENT else "production"
    odds_payloads = odds_snapshots = unmatched = 0
    summary = JobSummary()
    try:
        with (
            FileLock(config.state_dir / "principal-run.lock"),
            job_run(connection, "institutional.run", summary, config.mode.value) as run_id,
        ):
            if learning:
                summary.warnings.extend(learning.errors)
            additional_odds_dates = tuple(
                analysis_date for analysis_date in requested.dates if analysis_date != daily_odds_date
            )
            if not offline and ledger_mode == "production" and additional_odds_dates:
                with provider_client(config, connection) as client:
                    client.get_status(purpose="institutional_run_status", job_run_id=run_id)
                    odds_service = OddsIngestionService(
                        connection,
                        client,
                        dedupe_seconds=config.odds.snapshot_dedupe_seconds,
                    )
                    for analysis_date in additional_odds_dates:
                        fixture_count = connection.execute(
                            "SELECT count(*) FROM fixtures_current f JOIN competition_seasons cs "
                            "USING (competition_season_id) WHERE cs.ledger_mode=? AND cs.admitted "
                            "AND CAST(timezone(?, f.kickoff_utc) AS DATE)=? AND f.status_short IN ('NS','TBD')",
                            [ledger_mode, config.timezone, analysis_date],
                        ).fetchone()
                        if fixture_count and fixture_count[0]:
                            odds_result = odds_service.run(
                                analysis_date,
                                job_run_id=run_id,
                                ledger_mode=ledger_mode,
                                timezone=config.timezone,
                            )
                            odds_payloads += odds_result.payloads_seen
                            odds_snapshots += odds_result.snapshots_written
                            unmatched += odds_result.fixtures_not_in_ledger
                summary.odds_snapshots_written = odds_snapshots
            settlement = settle_completed_predictions(connection)
            shadow_settlement = settle_shadow_opportunities(connection)
            refresh_performance_rollups(connection)
            refresh_odds_age_research(connection)
            result = AnalysisService(
                connection,
                config.artifacts_dir / "reports",
                aged_reference_minutes=config.odds.aged_reference_minutes,
                minimum_probability_advantage=config.risk.minimum_probability_advantage,
                required_robust_ev=config.risk.minimum_expected_value,
                maximum_production_candidates_per_run=config.risk.maximum_simultaneous_recommendations,
                shadow_policy=config.shadow_candidates,
            ).run(
                requested.start,
                requested.end,
                timezone=config.timezone,
                ledger_mode=ledger_mode,
                job_run_id=run_id,
                report_mode="OFFLINE_REPLAY" if offline else "LIVE",
            )
            reference_row = connection.execute(
                "SELECT count(DISTINCT i.target_fixture_id) FROM institutional_predictions i "
                "JOIN institutional_opportunities o USING (prediction_id) "
                "WHERE CAST(i.analysis_run_id AS VARCHAR)=? AND o.latest_reference_odds IS NOT NULL",
                [result.analysis_run_id],
            ).fetchone()
            reference_fixtures = int(reference_row[0]) if reference_row else 0
            candidate_row = connection.execute(
                "SELECT count(*) FILTER (WHERE o.governance_state='PRODUCTION_ACTIONABLE'), "
                "count(*) FILTER (WHERE o.governance_state='SHADOW_ACTIONABLE'), "
                "count(*), count(*) FILTER (WHERE o.governance_state='RESEARCH_VALUE_SIGNAL') "
                "FROM institutional_predictions i JOIN institutional_opportunities o USING (prediction_id) "
                "WHERE CAST(i.analysis_run_id AS VARCHAR)=?",
                [result.analysis_run_id],
            ).fetchone()
            production_candidates = int(candidate_row[0]) if candidate_row else 0
            shadow_candidates = int(candidate_row[1]) if candidate_row else 0
            research_prices = int(candidate_row[2]) if candidate_row else 0
            research_value_signals = int(candidate_row[3]) if candidate_row else 0
            outside_analysis_snapshots_row = connection.execute(
                "SELECT count(*) FROM odds_snapshots s WHERE CAST(s.job_run_id AS VARCHAR)=? "
                "AND NOT EXISTS (SELECT 1 FROM institutional_predictions i "
                "WHERE CAST(i.analysis_run_id AS VARCHAR)=? AND i.target_fixture_id=s.fixture_id)",
                [run_id, result.analysis_run_id],
            ).fetchone()
            outside_analysis_snapshots = (
                int(outside_analysis_snapshots_row[0]) if outside_analysis_snapshots_row else 0
            )
            integrity_issues = audit_integrity(connection)
            if integrity_issues:
                summary.errors.extend(f"{issue.check}={issue.count}" for issue in integrity_issues)
                raise RuntimeError("Post-run warehouse integrity audit failed: " + ", ".join(summary.errors))
    finally:
        connection.close()
    newly_withheld = (
        len(set(learning.trained_versions) & set(learning.withheld_versions)) if learning else 0
    )
    typer.echo(
        f"Analysis {result.analysis_run_id}: {result.state}; expected={result.expected_fixtures}; "
        f"terminal={result.terminal_fixtures}; reference_fixtures={reference_fixtures}; "
        f"production_candidates={production_candidates}; shadow_candidates={shadow_candidates}; "
        f"research_prices={research_prices}; research_value_signals={research_value_signals}; "
        f"additional_odds_provider_rows={odds_payloads}; additional_odds_snapshots={odds_snapshots}; "
        f"additional_odds_snapshots_outside_analysis={outside_analysis_snapshots}; "
        f"unmatched_odds_fixtures={unmatched}; report={result.report_path}"
        f"; settled_predictions={settlement.predictions_settled}; "
        f"settled_shadow={shadow_settlement.opportunities_settled}; "
        f"ml_due={len(learning.due_models) if learning else 0}; "
        f"ml_trained={len(learning.trained_versions) if learning else 0}; "
        f"ml_promoted={len(learning.promoted_versions) if learning else 0}; "
        f"ml_newly_withheld={newly_withheld}; "
        f"promotion_pool_withheld={len(learning.withheld_versions) if learning else 0}"
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
    compare: bool = typer.Option(
        True,
        "--compare/--no-compare",
        help="Write paired out-of-fold comparisons when evaluating multiple models.",
    ),
) -> None:
    from sports_engine.cli.runtime import open_database
    from sports_engine.core.config import load_config
    from sports_engine.evaluation.comparison import compare_evaluation_reports
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
        minimum_competition_rows=config.models.promotion.minimum_competition_evaluation_rows,
        maximum_competition_ece=config.models.promotion.maximum_competition_expected_calibration_error,
    )
    try:
        reports = []
        for model_type in MODEL_TYPES if all_models else (model,):
            assert model_type is not None
            report = evaluator.evaluate(model_type, dataset_name=dataset, rolling_train_periods=rolling_periods)
            reports.append(report)
            typer.echo(
                f"{model_type}: folds={len(report.fold_metrics)} "
                f"log-loss={report.aggregate_metrics['log_loss']:.6f} report={report.path}"
            )
        if compare and len(reports) > 1:
            comparison = compare_evaluation_reports(
                [item.path for item in reports],
                config.artifacts_dir / "evaluation" / "comparisons",
                random_seed=config.models.random_seed,
            )
            typer.echo(f"paired-comparison={comparison}")
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    finally:
        connection.close()


@app.command("evaluate-score-calibration")
def evaluate_score_calibration(
    report: Path,
) -> None:
    """Evaluate a coherent Dixon-Coles intensity-scale challenger."""
    from sports_engine.core.config import load_config
    from sports_engine.evaluation.score_calibration import evaluate_score_intensity_calibration

    config = load_config()
    try:
        path = evaluate_score_intensity_calibration(
            report,
            config.artifacts_dir / "evaluation",
            random_seed=config.models.random_seed,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"score-calibration={path}")


@app.command("evaluate-competition-calibration")
def evaluate_competition_calibration(
    report: Path,
) -> None:
    """Evaluate a coherent partially pooled competition-intensity challenger."""
    from sports_engine.core.config import load_config
    from sports_engine.evaluation.competition_calibration import (
        evaluate_competition_intensity_calibration,
    )
    from sports_engine.warehouse.connection import connect

    config = load_config()
    connection = connect(config.database_path, read_only=True)
    try:
        path = evaluate_competition_intensity_calibration(
            connection,
            report,
            config.artifacts_dir / "evaluation",
            random_seed=config.models.random_seed,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    finally:
        connection.close()
    typer.echo(f"competition-calibration={path}")


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
