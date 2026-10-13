import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table

from sports_engine.cli.runtime import open_database, provider_client
from sports_engine.core.config import Environment, load_config
from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.access import production_access_probe
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.api_football.errors import ApiFootballPlanRestrictionError
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import pending_migrations

console = Console()


def run_doctor(connectivity: bool = False, verify_current_season: bool = False) -> bool:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python", sys.version_info >= (3, 12), sys.version.split()[0]))
    try:
        config = load_config()
        checks.append(("Configuration", True, "valid"))
    except Exception as exc:
        checks.append(("Configuration", False, str(exc)))
        config = None
    environment = Environment()
    checks.append(
        (
            "API key",
            bool(environment.api_football_key),
            "present" if environment.api_football_key else "missing",
        )
    )
    if config:
        for label, path in (
            ("Data directory", config.data_dir),
            ("Artifacts", config.artifacts_dir),
            ("State", config.state_dir),
            ("Logs", config.logs_dir),
        ):
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".write-probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                checks.append((label, True, str(path)))
            except OSError as exc:
                checks.append((label, False, str(exc)))
        try:
            connection = connect(config.database_path)
            connection.execute("SELECT 1").fetchone()
            pending = pending_migrations(connection)
            connection.close()
            checks.append(("DuckDB", True, "healthy"))
            checks.append(("Migrations", not pending, f"{len(pending)} pending" if pending else "current"))
        except Exception as exc:
            checks.append(("DuckDB", False, str(exc)))
        try:
            ZoneInfo(config.timezone)
            checks.append(("Timezone", True, config.timezone))
        except Exception as exc:
            checks.append(("Timezone", False, str(exc)))
    if connectivity and config and environment.api_football_key:
        try:
            connection = open_database(config)
            prior = connection.execute(
                "SELECT subscription_plan FROM provider_capabilities "
                "WHERE subscription_plan IS NOT NULL ORDER BY observed_at DESC LIMIT 1"
            ).fetchone()
            with provider_client(config, connection) as client:
                capabilities = client.get_status(purpose="doctor_connectivity")
                production_probe = production_access_probe(
                    connection,
                    datetime.now(ZoneInfo(config.timezone)).year,
                )
                subscription_changed = bool(
                    prior and prior[0] and capabilities.subscription_plan and prior[0] != capabilities.subscription_plan
                )
                should_probe = verify_current_season or subscription_changed
                if should_probe:
                    try:
                        teams = client.get(
                            Endpoint.TEAMS,
                            {"league": production_probe.league, "season": production_probe.season},
                            purpose="doctor_current_season_access",
                            priority=Priority.P0,
                        )
                        current_access = bool(teams)
                        current_access_detail = "available" if teams else "zero results"
                    except ApiFootballPlanRestrictionError as exc:
                        current_access = False
                        current_access_detail = f"BLOCKED_BY_PROVIDER_PLAN ({exc.provider_message})"
                else:
                    current_access = production_probe.stored_accessible is True
                    current_access_detail = (
                        "previously verified available"
                        if current_access
                        else "BLOCKED_BY_PROVIDER_PLAN (not re-probed)"
                    )
            replay = connection.execute(
                "SELECT bool_or(provider_accessible) FROM competition_seasons "
                "WHERE ledger_mode='replay' AND provider_season=?",
                [config.provider_access.replay_season],
            ).fetchone()
            connection.close()
            detail = (
                f"plan={capabilities.subscription_plan or 'unknown'}; "
                f"daily={capabilities.requests_used_today}/{capabilities.daily_limit}; "
                f"production league={production_probe.league} season={production_probe.season} "
                f"access={current_access_detail}; "
                f"replay {config.provider_access.replay_season} access="
                f"{('available' if replay[0] else 'blocked') if replay else 'not audited'}"
            )
            checks.append(("API connectivity", capabilities.subscription_active is not False, detail))
            checks.append(
                (
                    "Current-season access",
                    current_access or config.mode.value == "development",
                    current_access_detail,
                )
            )
        except Exception as exc:
            checks.append(("API connectivity", False, str(exc)))
    elif connectivity:
        checks.append(("API connectivity", False, "API key or configuration missing"))
    table = Table(title="Sports Engine Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for label, passed, detail in checks:
        table.add_row(label, "[green]PASS[/]" if passed else "[red]FAIL[/]", detail)
    console.print(table)
    return all(item[1] for item in checks)


def doctor_command(
    connectivity: bool = typer.Option(
        False,
        help="Refresh the provider's quota-free subscription status.",
    ),
    verify_current_season: bool = typer.Option(
        False,
        help="Explicitly spend one request verifying current-season data access.",
    ),
) -> None:
    if verify_current_season:
        connectivity = True
    if not run_doctor(connectivity, verify_current_season):
        raise typer.Exit(1)
