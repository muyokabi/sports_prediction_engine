import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import typer
import yaml
from rich.console import Console
from rich.table import Table

from sports_engine.cli.runtime import open_database, provider_client
from sports_engine.core.cleanup import run_scheduled_cleanup
from sports_engine.core.config import ApplicationMode, load_config
from sports_engine.core.exceptions import ProviderUnavailableError
from sports_engine.core.paths import project_root
from sports_engine.core.telemetry import JobSummary
from sports_engine.orchestration.locks import FileLock
from sports_engine.orchestration.runner import job_run
from sports_engine.sports.football.ingestion.backfill import (
    BackfillPlanner,
    RequestCappedProvider,
    reclassify_completed_results,
)
from sports_engine.sports.football.ingestion.coverage_gate import CoverageAuditService, SeasonCatalogService
from sports_engine.sports.football.ingestion.daily_update import DailyUpdateService
from sports_engine.sports.football.ingestion.detailed_matches import DetailedMatchIngestionService
from sports_engine.sports.football.ingestion.discovery import (
    DEFAULT_OBSERVATION_COLLECTION_LIMIT,
    CompetitionDiscoveryService,
    admit_observation_universe,
    backfill_candidate_universe,
)
from sports_engine.sports.football.ingestion.injuries import InjuryIngestionService
from sports_engine.sports.football.ingestion.odds import OddsIngestionService
from sports_engine.sports.football.ingestion.reconciliation import FixtureReconciliationService
from sports_engine.sports.football.ingestion.season_bootstrap import SeasonBootstrapService
from sports_engine.sports.football.quality.report import quality_details, quality_summary
from sports_engine.sports.football.quality.soak import CompletenessSoakService
from sports_engine.training.feedback import (
    refresh_performance_rollups,
    settle_completed_predictions,
    settle_shadow_opportunities,
)

app = typer.Typer(help="Football ingestion and quality workflows.")
coverage_app = typer.Typer(help="Competition coverage admission gate.")
odds_app = typer.Typer(help="Point-in-time bookmaker odds collection.")
app.add_typer(coverage_app, name="coverage")
app.add_typer(odds_app, name="odds")
console = Console()


def _ledger_target(config: Any) -> tuple[str, int | None]:
    if config.mode == ApplicationMode.DEVELOPMENT:
        return "replay", config.provider_access.replay_season
    return "production", None


def _backfill_detail_status(
    connection: Any,
    *,
    ledger_mode: str,
    selected_seasons: tuple[int, ...],
    historical: bool,
) -> dict[str, int]:
    season_parameters = list(selected_seasons) if historical else []
    season_filter = ""
    if season_parameters:
        placeholders = ",".join("?" for _ in season_parameters)
        season_filter = f"AND cs.provider_season IN ({placeholders}) "
    detail_row = connection.execute(
        "SELECT count(*) FILTER (WHERE f.status_short IN ('FT','AET','PEN')), "
        "count(*) FILTER (WHERE q.eligibility='ML_ELIGIBLE'), "
        "count(*) FILTER (WHERE q.eligibility='PENDING_REPAIR'), "
        "count(*) FILTER (WHERE f.status_short IN ('FT','AET','PEN') AND q.fixture_id IS NULL) "
        "FROM fixtures_current f JOIN competition_seasons cs USING (competition_season_id) "
        "LEFT JOIN fixture_quality_status q USING (fixture_id) WHERE cs.ledger_mode=? "
        f"{season_filter}",
        [ledger_mode, *season_parameters],
    ).fetchone()
    if detail_row is None:
        return {"completed": 0, "eligible": 0, "pending_repair": 0, "unassessed": 0}
    return {
        "completed": int(detail_row[0]),
        "eligible": int(detail_row[1]),
        "pending_repair": int(detail_row[2]),
        "unassessed": int(detail_row[3]),
    }


def _candidates() -> list[dict[str, Any]]:
    path = project_root() / "config/leagues/football_candidates.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast(list[dict[str, Any]], payload["candidates"])


@coverage_app.command("audit")
def coverage_audit(as_json: bool = typer.Option(False, "--json")) -> None:
    config = load_config()
    connection = open_database(config)
    summary = JobSummary()
    ledger_mode, replay_season = _ledger_target(config)
    try:
        with job_run(connection, "football.coverage_audit", summary, config.mode.value) as run_id:
            with provider_client(config, connection) as client:
                client.get_status(purpose="coverage_audit_status", job_run_id=run_id)
                result = CoverageAuditService(connection, client).run(
                    _candidates(),
                    job_run_id=run_id,
                    ledger_mode=ledger_mode,
                    replay_season=replay_season,
                )
            summary.requests_used = len(result.items)
            if not result.complete:
                summary.warnings.append(f"quota reserve stopped audit at candidate index {result.next_candidate_index}")
    finally:
        connection.close()
    results = [
        {
            "provider_id": item.provider_id,
            "name": item.name,
            "season": item.season,
            "accepted": item.accepted,
            "reason": item.reason,
            "replay_eligible": item.replay_eligible,
        }
        for item in result.items
    ]
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "complete": result.complete,
                    "next_candidate_index": result.next_candidate_index,
                    "items": results,
                }
            )
        )
        return
    table = Table(title=f"Football Coverage Audit ({config.mode.value}; ledger={ledger_mode})")
    for column in ("Competition", "Season", "Decision", "Reason"):
        table.add_column(column)
    for item in results:
        table.add_row(
            str(item["name"]),
            str(item.get("season", "-")),
            ("ACCEPT" if item["accepted"] else ("REPLAY_ONLY" if item["replay_eligible"] else "REJECT")),
            str(item["reason"]),
        )
    console.print(table)
    if not result.complete:
        console.print(
            f"[yellow]Stopped before protected quota reserve; resume begins at candidate "
            f"index {result.next_candidate_index}.[/]"
        )


@app.command("bootstrap")
def bootstrap() -> None:
    """Fetch current-season fixture skeletons for admitted competition-seasons."""
    config = load_config()
    connection = open_database(config)
    ledger_mode, _ = _ledger_target(config)
    admitted_count = connection.execute(
        "SELECT count(*) FROM competition_seasons WHERE provider_accessible AND ledger_mode=? "
        "AND CASE WHEN ?='replay' THEN replay_eligible ELSE admitted END",
        [ledger_mode, ledger_mode],
    ).fetchone()
    if not admitted_count or admitted_count[0] == 0:
        connection.close()
        console.print("No admitted competition-seasons. Run `football coverage audit` first.")
        raise typer.Exit(2)
    summary = JobSummary()
    try:
        with job_run(connection, "football.bootstrap", summary, config.mode.value) as run_id:
            with provider_client(config, connection) as client:
                client.get_status(purpose="bootstrap_status", job_run_id=run_id)
                result = SeasonBootstrapService(connection, client).run(job_run_id=run_id, ledger_mode=ledger_mode)
            summary.fixtures_discovered = result.fixtures_written
            summary.fixtures_updated = result.fixtures_written
            if not result.complete:
                summary.warnings.append(result.blocked_reason or "quota reserve stopped bootstrap")
    finally:
        connection.close()
    console.print(f"Bootstrapped {result.teams_written} teams and {result.fixtures_written} fixture records.")
    if not result.complete:
        if result.blocked_reason:
            console.print(f"[red]Provider access blocked: {result.blocked_reason}[/]")
            if config.mode == ApplicationMode.PRODUCTION:
                raise typer.Exit(3)
        else:
            console.print(
                f"[yellow]Stopped before protected quota reserve; resume index "
                f"{result.next_competition_index}, stage {result.next_stage}.[/]"
            )


def _state_summary(command: str) -> None:
    config = load_config()
    connection = open_database(config)
    row = connection.execute(
        "SELECT count(*), count(*) FILTER (WHERE q.eligibility='ML_ELIGIBLE'), "
        "count(*) FILTER (WHERE coalesce(q.eligibility, f.eligibility)='PENDING_REPAIR') "
        "FROM fixtures f LEFT JOIN fixture_quality_status q USING (fixture_id)"
    ).fetchone()
    connection.close()
    if row is None:
        raise RuntimeError("Fixture summary query returned no row")
    console.print(f"{command}: fixtures={row[0]} ml_eligible={row[1]} pending_repair={row[2]}")


@app.command("backfill")
def backfill() -> None:
    config = load_config()
    ledger_mode, _ = _ledger_target(config)
    connection = open_database(config)
    summary = JobSummary()
    try:
        with job_run(connection, "football.backfill", summary, config.mode.value) as run_id:
            with provider_client(config, connection) as client:
                capabilities = client.get_status(purpose="backfill_status", job_run_id=run_id)
                plan = BackfillPlanner(
                    connection,
                    client.quota_budget,
                    maximum_requests=config.backfill.maximum_requests_per_run,
                    repair_attempt_limit=config.backfill.repair_attempt_limit,
                ).plan(ledger_mode=ledger_mode)
                if plan.fixture_ids:
                    capped_client = RequestCappedProvider(client, plan.request_budget)
                    result = DetailedMatchIngestionService(
                        connection,
                        capped_client,
                        config.data_dir / "quarantine",
                    ).run(plan.fixture_ids, job_run_id=run_id)
                else:
                    result = None
            summary.fixtures_enriched = result.fixtures_eligible if result else 0
            summary.fixtures_quarantined = result.fixtures_quarantined if result else 0
    finally:
        connection.close()
    console.print(
        f"Backfill: candidates={plan.candidate_count} request_budget={plan.request_budget} "
        f"selected={len(plan.fixture_ids)} eligible={result.fixtures_eligible if result else 0} "
        f"quarantined={result.fixtures_quarantined if result else 0} "
        f"daily_remaining={capabilities.daily_remaining}."
    )


@app.command("historical-backfill")
def historical_backfill(
    season: int = typer.Option(..., min=2000, max=2100, help="Registered replay season to enrich."),
    max_requests: int = typer.Option(1000, min=1, max=5000, help="Hard request cap for this run."),
) -> None:
    """Enrich a registered replay season without changing the production fixture universe."""
    config = load_config()
    connection = open_database(config)
    registered = connection.execute(
        "SELECT count(*) FROM competition_seasons WHERE ledger_mode='replay' "
        "AND provider_season=? AND replay_eligible AND provider_accessible",
        [season],
    ).fetchone()
    if not registered or not registered[0]:
        connection.close()
        console.print(f"[red]Replay season {season} is not registered and provider-qualified.[/]")
        raise typer.Exit(2)
    summary = JobSummary()
    try:
        with (
            FileLock(config.state_dir / f"historical_backfill_{season}.lock"),
            job_run(connection, f"football.historical_backfill.{season}", summary, config.mode.value) as run_id,
        ):
            with provider_client(config, connection) as client:
                capabilities = client.get_status(purpose=f"historical_backfill_status:{season}", job_run_id=run_id)
                plan = BackfillPlanner(
                    connection,
                    client.quota_budget,
                    maximum_requests=max_requests,
                    repair_attempt_limit=config.backfill.repair_attempt_limit,
                ).plan(ledger_mode="replay", provider_season=season)
                result = None
                if plan.fixture_ids:
                    capped_client = RequestCappedProvider(client, plan.request_budget)
                    result = DetailedMatchIngestionService(
                        connection,
                        capped_client,
                        config.data_dir / "quarantine",
                    ).run(plan.fixture_ids, job_run_id=run_id)
            summary.fixtures_enriched = result.fixtures_eligible if result else 0
            summary.fixtures_quarantined = result.fixtures_quarantined if result else 0
    finally:
        connection.close()
    console.print(
        f"Historical backfill {season}: candidates={plan.candidate_count} request_budget={plan.request_budget} "
        f"selected={len(plan.fixture_ids)} eligible={result.fixtures_eligible if result else 0} "
        f"quarantined={result.fixtures_quarantined if result else 0} "
        f"daily_remaining_at_start={capabilities.daily_remaining}."
    )


@app.command("historical-register")
def historical_register(
    season: int = typer.Option(..., min=2000, max=2100, help="Historical season to register and bootstrap."),
) -> None:
    """Coverage-qualify and bootstrap one replay season without changing application mode."""
    config = load_config()
    connection = open_database(config)
    summary = JobSummary()
    try:
        with (
            FileLock(config.state_dir / f"historical_register_{season}.lock"),
            job_run(connection, f"football.historical_register.{season}", summary, config.mode.value) as run_id,
        ):
            with provider_client(config, connection) as client:
                client.get_status(purpose=f"historical_register_status:{season}", job_run_id=run_id)
                coverage = CoverageAuditService(connection, client).run(
                    _candidates(),
                    job_run_id=run_id,
                    ledger_mode="replay",
                    replay_season=season,
                )
                bootstrap_result = SeasonBootstrapService(connection, client).run(
                    job_run_id=run_id,
                    ledger_mode="replay",
                    provider_season=season,
                )
            summary.requests_used = len(coverage.items)
            summary.fixtures_discovered = bootstrap_result.fixtures_written
            summary.fixtures_updated = bootstrap_result.fixtures_written
            if not coverage.complete or not bootstrap_result.complete:
                summary.warnings.append("historical registration stopped before completion")
    finally:
        connection.close()
    eligible = sum(item.replay_eligible for item in coverage.items)
    console.print(
        f"Historical register {season}: coverage_eligible={eligible}/{len(coverage.items)} "
        f"competition_seasons={bootstrap_result.competition_seasons_completed} "
        f"teams={bootstrap_result.teams_written} fixtures={bootstrap_result.fixtures_written} "
        f"complete={coverage.complete and bootstrap_result.complete}."
    )


@app.command("fetch-backfill")
def fetch_backfill(
    season: int | None = typer.Option(
        None,
        "--season",
        min=2000,
        max=2100,
        help="Historical season to fetch into the replay ledger; omit for the configured current ledger.",
    ),
    past_seasons: int | None = typer.Option(
        None,
        "--past-seasons",
        min=1,
        max=10,
        help="Latest N completed seasons for every selected league; mutually exclusive with --season.",
    ),
    max_requests: int = typer.Option(
        1000,
        "--max-requests",
        min=1,
        max=5000,
        help="Hard cap for detailed backfill requests; coverage and fixture fetching are not included.",
    ),
    league_limit: int = typer.Option(
        40,
        "--league-limit",
        min=1,
        max=200,
        help="Maximum discovered leagues considered; admitted leagues are selected first.",
    ),
    discovery_enabled: bool = typer.Option(
        True,
        "--discovery/--no-discovery",
        help="Refresh league discovery before coverage; disable only when resuming from persisted discovery.",
    ),
    coverage_enabled: bool = typer.Option(
        True,
        "--coverage/--no-coverage",
        help="Run the provider coverage/admission check before fetching fixtures.",
    ),
    bootstrap_enabled: bool = typer.Option(
        True,
        "--bootstrap/--no-bootstrap",
        help="Fetch teams and season fixture skeletons before detailed backfill.",
    ),
) -> None:
    """Register, fetch, and enrich selected current or historical seasons."""
    if season is not None and past_seasons is not None:
        console.print("[red]Use --season or --past-seasons, not both.[/]")
        raise typer.Exit(2)
    config = load_config()
    configured_ledger, configured_replay_season = _ledger_target(config)
    historical = season is not None or past_seasons is not None or configured_ledger == "replay"
    ledger_mode = "replay" if historical else "production"
    exact_season = season if season is not None else configured_replay_season if configured_ledger == "replay" else None

    connection = open_database(config)
    summary = JobSummary()
    catalog_result = None
    discovery_result = None
    candidate_universe = _candidates()
    bootstrap_results = []
    backfill_result = None
    reclassified_results = 0
    detail_status = {"completed": 0, "eligible": 0, "pending_repair": 0, "unassessed": 0}
    label = f"last-{past_seasons}" if past_seasons is not None else str(exact_season or "current")
    try:
        with (
            FileLock(config.state_dir / f"fetch_backfill_{ledger_mode}_{label}.lock"),
            job_run(connection, f"football.fetch_backfill.{ledger_mode}.{label}", summary, config.mode.value) as run_id,
        ):
            with provider_client(config, connection) as client:
                capabilities = client.get_status(purpose=f"fetch_backfill_status:{label}", job_run_id=run_id)
                if discovery_enabled:
                    discovery_result = CompetitionDiscoveryService(connection, client).run(job_run_id=run_id)
                discovered_candidates = backfill_candidate_universe(connection, limit=league_limit)
                if discovered_candidates:
                    candidate_universe = discovered_candidates
                if coverage_enabled:
                    catalog_result = SeasonCatalogService(connection, client).run(
                        candidate_universe,
                        job_run_id=run_id,
                        current=not historical,
                        exact_season=exact_season,
                        past_seasons=past_seasons,
                    )
                if catalog_result is not None:
                    selected_seasons = catalog_result.provider_seasons
                elif past_seasons is not None:
                    rows = connection.execute(
                        "SELECT DISTINCT provider_season FROM competition_seasons "
                        "WHERE ledger_mode='replay' AND replay_eligible "
                        "ORDER BY provider_season DESC LIMIT ?",
                        [past_seasons],
                    ).fetchall()
                    selected_seasons = tuple(int(row[0]) for row in rows)
                elif exact_season is not None:
                    selected_seasons = (exact_season,)
                else:
                    selected_seasons = ()
                if bootstrap_enabled:
                    bootstrap_targets = selected_seasons if historical else (None,)
                    for bootstrap_season in bootstrap_targets:
                        result = SeasonBootstrapService(connection, client).run(
                            job_run_id=run_id,
                            ledger_mode=ledger_mode,
                            provider_season=bootstrap_season,
                        )
                        bootstrap_results.append(result)
                        if not result.complete:
                            break
                reclassified_results = reclassify_completed_results(
                    connection,
                    ledger_mode=ledger_mode,
                    provider_seasons=selected_seasons if historical else None,
                )
                plan = BackfillPlanner(
                    connection,
                    client.quota_budget,
                    maximum_requests=max_requests,
                    repair_attempt_limit=config.backfill.repair_attempt_limit,
                ).plan(
                    ledger_mode=ledger_mode,
                    provider_seasons=selected_seasons if historical else None,
                )
                if plan.fixture_ids:
                    capped_client = RequestCappedProvider(client, plan.request_budget)
                    backfill_result = DetailedMatchIngestionService(
                        connection,
                        capped_client,
                        config.data_dir / "quarantine",
                    ).run(plan.fixture_ids, job_run_id=run_id)
                detail_status = _backfill_detail_status(
                    connection,
                    ledger_mode=ledger_mode,
                    selected_seasons=selected_seasons,
                    historical=historical,
                )
            summary.requests_used = int(discovery_result is not None) + int(catalog_result is not None)
            summary.fixtures_discovered = sum(result.fixtures_written for result in bootstrap_results)
            summary.fixtures_updated = summary.fixtures_discovered
            for result in bootstrap_results:
                if not result.complete:
                    summary.warnings.append(result.blocked_reason or "season bootstrap stopped before completion")
            summary.fixtures_enriched = backfill_result.fixtures_eligible if backfill_result else 0
            summary.fixtures_quarantined = backfill_result.fixtures_quarantined if backfill_result else 0
            outstanding = detail_status["pending_repair"] + detail_status["unassessed"]
            if outstanding:
                summary.warnings.append(
                    f"optional historical detail remains incomplete for {outstanding} completed fixtures; "
                    "completed scores remain available to the statistical models"
                )
    except ProviderUnavailableError as exc:
        console.print(
            "[yellow]API-Football is temporarily unreachable after retries. "
            "Completed work and the exact bootstrap/backfill checkpoint were preserved. "
            "Rerun the same fetch-backfill command to continue.[/]"
        )
        console.print(f"[dim]{exc}[/]")
        raise typer.Exit(2) from None
    finally:
        connection.close()

    coverage_eligible = (
        sum(item.replay_eligible if historical else item.accepted for item in catalog_result.items)
        if catalog_result is not None
        else 0
    )
    coverage_text = "skipped" if catalog_result is None else f"{coverage_eligible}/{len(catalog_result.items)} eligible"
    bootstrap_text = (
        "skipped"
        if not bootstrap_results
        else f"teams={sum(result.teams_written for result in bootstrap_results)} "
        f"fixtures={sum(result.fixtures_written for result in bootstrap_results)} "
        f"complete={all(result.complete for result in bootstrap_results)}"
    )
    console.print(
        f"Fetch + backfill: ledger={ledger_mode} season={label} coverage={coverage_text} "
        f"discovered={discovery_result.discovered if discovery_result else 'persisted'} "
        f"league_universe={len(candidate_universe)} "
        f"bootstrap=({bootstrap_text}) candidates={plan.candidate_count} "
        f"request_budget={plan.request_budget} selected={len(plan.fixture_ids)} "
        f"locally_reclassified={reclassified_results} "
        f"eligible={backfill_result.fixtures_eligible if backfill_result else 0} "
        f"quarantined={backfill_result.fixtures_quarantined if backfill_result else 0} "
        f"detail_coverage={detail_status['eligible']}/{detail_status['completed']} "
        f"pending_repair={detail_status['pending_repair']} unassessed={detail_status['unassessed']} "
        f"daily_remaining_at_start={capabilities.daily_remaining}."
    )
    if detail_status["pending_repair"] or detail_status["unassessed"]:
        console.print(
            "[yellow]The requested seasons and completed scores are registered for modelling. Optional "
            "match enrichment is incomplete; rerunning is not required for score-model training.[/]"
        )


@app.command("enrich")
def enrich(limit: int = typer.Option(20, min=1, max=200)) -> None:
    """Fetch batched full-match packages for completed fixtures needing detail."""
    config = load_config()
    ledger_mode, _ = _ledger_target(config)
    connection = open_database(config)
    rows = connection.execute(
        "SELECT f.provider_fixture_id FROM fixtures_current f "
        "JOIN competition_seasons cs USING (competition_season_id) "
        "LEFT JOIN fixture_quality_status q USING (fixture_id) "
        "LEFT JOIN fixture_repair_state r USING (fixture_id) "
        "WHERE cs.ledger_mode=? AND f.status_short IN ('FT', 'AET', 'PEN') "
        "AND coalesce(q.eligibility, 'PENDING_REPAIR')='PENDING_REPAIR' "
        "AND coalesce(r.attempt_count, 0) < ? "
        "AND (r.next_retry_after IS NULL OR r.next_retry_after <= current_timestamp) "
        "ORDER BY f.kickoff_utc LIMIT ?",
        [ledger_mode, config.backfill.repair_attempt_limit, limit],
    ).fetchall()
    fixture_ids = [int(row[0]) for row in rows]
    if not fixture_ids:
        connection.close()
        console.print("No completed fixtures currently require detailed enrichment.")
        return
    summary = JobSummary()
    try:
        with job_run(connection, "football.enrich", summary, config.mode.value) as run_id:
            with provider_client(config, connection) as client:
                client.get_status(purpose="enrichment_status", job_run_id=run_id)
                result = DetailedMatchIngestionService(
                    connection,
                    client,
                    config.data_dir / "quarantine",
                ).run(fixture_ids, job_run_id=run_id)
            summary.fixtures_updated = result.fixtures_received
            if result.fixtures_quarantined:
                summary.warnings.append(f"{result.fixtures_quarantined} match packages quarantined")
    finally:
        connection.close()
    console.print(
        f"Detailed matches: received={result.fixtures_received} "
        f"ml_eligible={result.fixtures_eligible} quarantined={result.fixtures_quarantined}."
    )


@app.command("daily")
def daily(
    as_of: str | None = typer.Option(None, help="Operational date (required only to override replay time)."),
) -> Any:
    from sports_engine.markets.decision import EvidencePolicy, RiskPolicy
    from sports_engine.sports.football.prediction.service import PredictionService
    from sports_engine.training.continuous import run_due_ml_updates

    config = load_config()
    cleanup_result = run_scheduled_cleanup(config)
    if cleanup_result.ran and cleanup_result.removed:
        console.print(
            f"Generated-file cleanup: removed={len(cleanup_result.removed)} bytes={cleanup_result.bytes_removed}."
        )
    if cleanup_result.errors:
        console.print(f"[yellow]Generated-file cleanup warning: {'; '.join(cleanup_result.errors)}[/]")
    connection = open_database(config)
    ledger_mode, replay_season = _ledger_target(config)
    if as_of is not None:
        operational_date = date.fromisoformat(as_of)
    elif config.mode == ApplicationMode.PRODUCTION:
        operational_date = datetime.now(ZoneInfo(config.timezone)).date()
    else:
        latest = connection.execute(
            "SELECT max(CAST(f.kickoff_utc AS DATE)) FROM fixtures_current f "
            "JOIN competition_seasons cs USING (competition_season_id) WHERE cs.ledger_mode='replay'"
        ).fetchone()
        if latest is None or latest[0] is None:
            connection.close()
            console.print("Replay ledger is empty. Run coverage audit and bootstrap, or provide --as-of.")
            raise typer.Exit(2)
        operational_date = latest[0]
    summary = JobSummary()
    try:
        with (
            FileLock(config.state_dir / "football_daily.lock"),
            job_run(connection, "football.daily", summary, config.mode.value) as run_id,
        ):
            with provider_client(config, connection) as client:
                capabilities = client.get_status(purpose="daily_status", job_run_id=run_id)
                discovery_result = (
                    CompetitionDiscoveryService(connection, client).run(job_run_id=run_id)
                    if ledger_mode == "production"
                    else None
                )
                observation_admitted = (
                    admit_observation_universe(
                        connection,
                        limit=DEFAULT_OBSERVATION_COLLECTION_LIMIT,
                    )
                    if ledger_mode == "production"
                    else []
                )
                eligibility = "replay_eligible" if ledger_mode == "replay" else "admitted"
                registered = connection.execute(
                    f"SELECT count(*) FROM competition_seasons WHERE ledger_mode=? "
                    f"AND provider_accessible AND {eligibility}",
                    [ledger_mode],
                ).fetchone()
                initial_bootstrap = None
                if not registered or not registered[0]:
                    # A fresh installation has no admitted fixture universe.
                    # Register the configured selected leagues from one catalog
                    # response, then fetch their teams and fixture skeletons.
                    SeasonCatalogService(connection, client).run(
                        _candidates(),
                        current=ledger_mode == "production",
                        exact_season=replay_season if ledger_mode == "replay" else None,
                        job_run_id=run_id,
                    )
                    initial_bootstrap = SeasonBootstrapService(connection, client).run(
                        job_run_id=run_id,
                        ledger_mode=ledger_mode,
                        provider_season=replay_season if ledger_mode == "replay" else None,
                    )
                result = DailyUpdateService(
                    connection,
                    client,
                    config.data_dir / "quarantine",
                    repair_attempt_limit=config.backfill.repair_attempt_limit,
                ).run_catch_up(
                    operational_date,
                    ledger_mode=ledger_mode,
                    job_run_id=run_id,
                )
                odds_result = None
                odds_date = operational_date + timedelta(days=config.odds.target_days_ahead)
                odds_ready = connection.execute(
                    "SELECT count(*) FROM fixtures_current f "
                    "JOIN competition_seasons cs USING (competition_season_id) "
                    "WHERE cs.ledger_mode=? AND CAST(f.kickoff_utc AS DATE)=? "
                    "AND coalesce(CAST(json_extract(cs.coverage, '$.odds') AS BOOLEAN), false)",
                    [ledger_mode, odds_date],
                ).fetchone()
                if odds_ready and odds_ready[0] > 0:
                    odds_result = OddsIngestionService(
                        connection,
                        client,
                        dedupe_seconds=config.odds.snapshot_dedupe_seconds,
                    ).run(
                        odds_date,
                        job_run_id=run_id,
                        ledger_mode=ledger_mode,
                        timezone=config.timezone,
                    )
                injury_result = None
                injury_ready = connection.execute(
                    "SELECT count(*) FROM fixtures_current f "
                    "JOIN competition_seasons cs USING (competition_season_id) "
                    "WHERE cs.ledger_mode=? AND CAST(f.kickoff_utc AS DATE)=? "
                    "AND coalesce(CAST(json_extract(cs.coverage, '$.injuries') AS BOOLEAN), false)",
                    [ledger_mode, odds_date],
                ).fetchone()
                if injury_ready and injury_ready[0] > 0:
                    injury_result = InjuryIngestionService(connection, client).run(odds_date, job_run_id=run_id)
                backfill_plan = BackfillPlanner(
                    connection,
                    client.quota_budget,
                    # Prediction runs must remain operationally bounded. The
                    # dedicated backfill command retains the larger maintenance
                    # budget; daily runs continuously chip away at the ledger.
                    maximum_requests=config.backfill.maximum_daily_requests_per_run,
                    repair_attempt_limit=config.backfill.repair_attempt_limit,
                ).plan(ledger_mode=ledger_mode)
                backfill_result = None
                if backfill_plan.fixture_ids:
                    capped_client = RequestCappedProvider(client, backfill_plan.request_budget)
                    backfill_result = DetailedMatchIngestionService(
                        connection, capped_client, config.data_dir / "quarantine"
                    ).run(backfill_plan.fixture_ids, job_run_id=run_id)
            summary.fixtures_discovered = result.relevant_fixtures
            summary.fixtures_updated = result.fixture_records_written
            if initial_bootstrap is not None:
                summary.fixtures_discovered += initial_bootstrap.fixtures_written
                summary.fixtures_updated += initial_bootstrap.fixtures_written
                if not initial_bootstrap.complete:
                    summary.warnings.append(initial_bootstrap.blocked_reason or "initial bootstrap incomplete")
            summary.fixtures_enriched = result.enrichment.fixtures_eligible + (
                backfill_result.fixtures_eligible if backfill_result else 0
            )
            summary.fixtures_quarantined = result.enrichment.fixtures_quarantined + (
                backfill_result.fixtures_quarantined if backfill_result else 0
            )
            summary.odds_snapshots_written = odds_result.snapshots_written if odds_result else 0
            if odds_result and odds_result.blocked_reason:
                summary.warnings.append(odds_result.blocked_reason)
            settlement_result = settle_completed_predictions(connection)
            shadow_settlement_result = settle_shadow_opportunities(connection)
            refresh_performance_rollups(connection)
            learning = run_due_ml_updates(connection, config, ledger_mode=ledger_mode)
            summary.warnings.extend(learning.errors)
            if injury_result and injury_result.ignored_unknown_teams:
                summary.warnings.append(f"{injury_result.ignored_unknown_teams} injury rows ignored for unknown teams")
            champion = connection.execute("SELECT count(*) FROM model_runs WHERE status='champion'").fetchone()
            tomorrow_fixtures = connection.execute(
                "SELECT count(*) FROM fixtures_current f JOIN competition_seasons cs "
                "USING (competition_season_id) WHERE cs.ledger_mode=? "
                "AND CAST(timezone(?, f.kickoff_utc) AS DATE)=? "
                "AND f.status_short IN ('NS', 'TBD')",
                [ledger_mode, config.timezone, odds_date],
            ).fetchone()
            prediction_result = None
            if champion and champion[0] and tomorrow_fixtures and tomorrow_fixtures[0]:
                prediction_result = PredictionService(
                    connection,
                    windows=config.features.windows,
                    exponential_half_life=config.features.exponential_half_life,
                    prediction_lead_hours=config.features.prediction_lead_hours,
                    historical_ledger_modes=config.models.historical_training_ledgers,
                    evidence_policy=EvidencePolicy(
                        0,
                        0,
                        0,
                        0,
                        config.models.minimum_team_history,
                        config.models.require_calibration_for_betting,
                        config.models.minimum_prediction_confidence,
                    ),
                    risk_policy=RiskPolicy(
                        config.risk.maximum_bankroll_fraction_per_wager,
                        config.risk.maximum_daily_exposure,
                        config.risk.maximum_simultaneous_recommendations,
                        config.risk.fractional_kelly,
                        config.risk.hard_stake_cap,
                        config.risk.minimum_probability_advantage,
                        config.risk.minimum_expected_value,
                    ),
                ).predict(odds_date, ledger_mode=ledger_mode, timezone=config.timezone)
    finally:
        connection.close()
    console.print(
        f"Football daily: plan={capabilities.subscription_plan} "
        f"daily_remaining={capabilities.daily_remaining} minute_remaining={capabilities.minute_remaining} "
        f"date={operational_date} discovered={result.relevant_fixtures} "
        f"catalog_discovered={discovery_result.discovered if discovery_result else 0} "
        f"observation_admitted={len(observation_admitted)} "
        f"completed={result.completed_candidates} enriched={result.enrichment.fixtures_eligible} "
        f"quarantined={result.enrichment.fixtures_quarantined} "
        f"backfill={backfill_result.fixtures_eligible if backfill_result else 0} "
        f"predictions={prediction_result.fixture_count if prediction_result else 0}"
        f" settled_predictions={settlement_result.predictions_settled}"
        f" settled_shadow={shadow_settlement_result.opportunities_settled}"
        f" ml_due={len(learning.due_models)} ml_trained={len(learning.trained_versions)}"
        f" ml_promoted={len(learning.promoted_versions)} ml_withheld={len(learning.withheld_versions)}"
    )
    return learning


@app.command("reconcile")
def reconcile() -> None:
    config = load_config()
    connection = open_database(config)
    summary = JobSummary()
    ledger_mode, _ = _ledger_target(config)
    try:
        with job_run(connection, "football.reconcile", summary, config.mode.value) as run_id:
            with provider_client(config, connection) as client:
                client.get_status(purpose="reconciliation_status", job_run_id=run_id)
                result = FixtureReconciliationService(connection, client).run(
                    job_run_id=run_id, ledger_mode=ledger_mode
                )
            summary.fixtures_discovered = result.fixtures_seen
            summary.fixtures_updated = result.observations_added
            if not result.complete:
                summary.warnings.append(
                    f"quota reserve stopped reconciliation at index {result.next_competition_index}"
                )
    finally:
        connection.close()
    console.print(
        f"Reconciled {result.fixtures_seen} fixtures; {result.observations_added} changed observations persisted."
    )


@app.command("seasons")
def seasons() -> None:
    config = load_config()
    connection = open_database(config)
    rows = connection.execute(
        "SELECT c.name, cs.provider_season, cs.ledger_mode, cs.admitted, cs.replay_eligible, "
        "cs.provider_accessible, "
        "coalesce(cs.access_reason, cs.admission_reason) FROM competition_seasons cs "
        "JOIN competitions c USING (competition_id) ORDER BY c.name, cs.provider_season"
    ).fetchall()
    connection.close()
    table = Table("Competition", "Season", "Ledger", "Production admitted", "Replay eligible", "Accessible", "Reason")
    for row in rows:
        table.add_row(*(str(value) for value in row))
    console.print(table)


@app.command("season-rollover")
def season_rollover() -> None:
    """Discover and coverage-gate newly current seasons without altering prior seasons."""
    config = load_config()
    connection = open_database(config)
    summary = JobSummary()
    try:
        with job_run(connection, "football.season_rollover", summary, "production") as run_id:
            with provider_client(config, connection) as client:
                client.get_status(purpose="season_rollover_status", job_run_id=run_id)
                result = CoverageAuditService(connection, client).run(
                    _candidates(), job_run_id=run_id, ledger_mode="production"
                )
            summary.requests_used = len(result.items)
            if not result.complete:
                summary.warnings.append(f"quota reserve stopped rollover at index {result.next_candidate_index}")
    finally:
        connection.close()
    accepted = sum(item.accepted for item in result.items)
    rejected = len(result.items) - accepted
    console.print(
        f"Season discovery assessed {len(result.items)} candidates: {accepted} coverage-qualified, {rejected} rejected."
    )


@app.command("quality")
def quality(
    summary: bool = typer.Option(True, "--summary/--no-summary"),
    detailed: bool = typer.Option(False, "--detailed"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    config = load_config()
    connection = open_database(config)
    summaries = quality_summary(connection) if summary else []
    details = quality_details(connection) if detailed else []
    connection.close()
    if as_json:
        # Rich decodes JSON escapes before writing and can therefore fail on
        # legacy Windows consoles whose code page cannot represent a provider
        # competition name. Keep machine output ASCII-safe and unstyled.
        typer.echo(
            json.dumps(
                {"summary": [asdict(item) for item in summaries], "details": details},
                default=str,
                ensure_ascii=True,
            )
        )
        return
    if summary:
        table = Table(
            "Competition",
            "Season",
            "Ledger",
            "Total",
            "Final",
            "Enriched",
            "Eligible",
            "Repair",
            "Quarantine",
            "Unavailable",
            "Complete %",
            "Common missing",
        )
        for item in summaries:
            table.add_row(
                item.competition,
                str(item.season),
                item.ledger_mode,
                str(item.total),
                str(item.completed),
                str(item.enriched),
                str(item.ml_eligible),
                str(item.pending_repair),
                str(item.quarantined),
                str(item.unavailable_components),
                f"{item.completeness_percentage:.1f}",
                ", ".join(f"{name}:{count}" for name, count in item.common_missing) or "-",
            )
        console.print(table)
    if detailed:
        table = Table("Competition", "Season", "Fixture", "Component", "State")
        for row in details:
            table.add_row(*(str(value) for value in row))
        console.print(table)


@app.command("quality-soak")
def quality_soak(
    leagues: int = typer.Option(3, min=1, max=10),
    fixtures_per_league: int = typer.Option(2, min=1, max=5),
) -> None:
    """Run a quota-conscious real-provider completeness sample."""
    config = load_config()
    ledger_mode, _ = _ledger_target(config)
    connection = open_database(config)
    summary = JobSummary()
    try:
        with job_run(connection, "football.quality_soak", summary, config.mode.value) as run_id:
            with provider_client(config, connection) as client:
                capabilities = client.get_status(purpose="quality_soak_status", job_run_id=run_id)
                result = CompletenessSoakService(
                    connection,
                    client,
                    config.data_dir / "quarantine",
                    config.artifacts_dir / "reports",
                ).run(
                    ledger_mode=ledger_mode,
                    league_limit=leagues,
                    fixtures_per_league=fixtures_per_league,
                    repair_attempt_limit=config.backfill.repair_attempt_limit,
                    job_run_id=run_id,
                )
                if client.capabilities is not None:
                    capabilities = client.capabilities
            summary.fixtures_enriched = result.ml_eligible
            summary.fixtures_quarantined = result.quarantined
    finally:
        connection.close()
    table = Table(
        "Competition",
        "Season",
        "Sampled",
        "Assessed",
        "Unassessed",
        "Eligible",
        "Quarantine",
        "Repairs",
        "Missing",
        "Nulls",
    )
    for item in result.leagues:
        table.add_row(
            item.competition,
            str(item.season),
            str(item.fixtures_sampled),
            str(item.fixtures_assessed),
            str(item.fixtures_unassessed),
            str(item.ml_eligible),
            str(item.quarantined),
            f"{item.repairs_succeeded}/{item.repairs_attempted}",
            ", ".join(f"{key}:{value}" for key, value in item.missing_components.items()) or "-",
            ", ".join(f"{key}:{value}" for key, value in item.provider_nulls.items() if value) or "-",
        )
    console.print(table)
    console.print(
        f"Soak sampled={result.fixtures_sampled} assessed={result.fixtures_assessed} "
        f"unassessed={result.fixtures_unassessed} eligible={result.ml_eligible} "
        f"quarantined={result.quarantined} daily_remaining={capabilities.daily_remaining} "
        f"report={result.report_path}"
    )


@odds_app.command("tomorrow")
def odds_tomorrow(target_date: str | None = typer.Option(None, "--date")) -> None:
    """Collect all paginated odds for a date as immutable snapshots."""
    config = load_config()
    ledger_mode, _ = _ledger_target(config)
    connection = open_database(config)
    coverage = connection.execute(
        "SELECT count(*) FROM competition_seasons WHERE ledger_mode=? "
        "AND coalesce(CAST(json_extract(coverage, '$.odds') AS BOOLEAN), false)",
        [ledger_mode],
    ).fetchone()
    if not coverage or coverage[0] == 0:
        connection.close()
        console.print(f"No {ledger_mode} competition-season advertises odds coverage; no provider request made.")
        raise typer.Exit(2)
    requested_date = (
        date.fromisoformat(target_date)
        if target_date
        else datetime.now(ZoneInfo(config.timezone)).date() + timedelta(days=config.odds.target_days_ahead)
    )
    summary = JobSummary()
    try:
        with job_run(connection, "football.odds", summary, config.mode.value) as run_id:
            with provider_client(config, connection) as client:
                capabilities = client.get_status(purpose="odds_status", job_run_id=run_id)
                result = OddsIngestionService(
                    connection,
                    client,
                    dedupe_seconds=config.odds.snapshot_dedupe_seconds,
                ).run(
                    requested_date,
                    job_run_id=run_id,
                    ledger_mode=ledger_mode,
                    timezone=config.timezone,
                )
            summary.odds_snapshots_written = result.snapshots_written
    finally:
        connection.close()
    console.print(
        f"Odds {requested_date}: payloads={result.payloads_seen} "
        f"snapshots={result.snapshots_written} unknown_fixtures={result.fixtures_not_in_ledger} "
        f"daily_remaining={capabilities.daily_remaining}."
    )
