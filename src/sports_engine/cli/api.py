import json

import typer
from rich.console import Console
from rich.table import Table

from sports_engine.cli.runtime import open_database, provider_client
from sports_engine.core.config import load_config

app = typer.Typer(help="Provider API status and quota accounting.")
console = Console()


@app.command("quota")
def quota(as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON.")) -> None:
    """Show the last observed quota without consuming an API request."""
    connection = open_database(load_config())
    row = connection.execute(
        "SELECT provider, subscription_plan, subscription_active, requests_limit_daily, "
        "requests_current, daily_remaining, minute_limit, minute_remaining, observed_at "
        "FROM provider_capabilities ORDER BY observed_at DESC LIMIT 1"
    ).fetchone()
    connection.close()
    if row is None:
        console.print("No provider quota observation has been recorded yet.")
        raise typer.Exit(2)
    payload = {
        "provider": row[0],
        "plan": row[1],
        "subscription_active": row[2],
        "daily_limit": row[3],
        "daily_used": row[4],
        "daily_remaining": row[5],
        "minute_limit": row[6],
        "minute_remaining": row[7],
        "observed_at": row[8].isoformat() if row[8] else None,
    }
    if as_json:
        console.print_json(json.dumps(payload))
        return
    table = Table(title="API-Football Quota")
    table.add_column("Field")
    table.add_column("Value")
    for label, key in (
        ("Plan", "plan"),
        ("Subscription active", "subscription_active"),
        ("Daily limit", "daily_limit"),
        ("Daily used", "daily_used"),
        ("Daily remaining", "daily_remaining"),
        ("Per-minute limit", "minute_limit"),
        ("Per-minute remaining", "minute_remaining"),
        ("Last observed", "observed_at"),
    ):
        value = payload[key]
        table.add_row(label, f"{value:,}" if isinstance(value, int) else str(value))
    console.print(table)


@app.command("capabilities")
def capabilities(as_json: bool = typer.Option(False, "--json")) -> None:
    """Show plan/quota and the separately tracked production and replay access states."""
    config = load_config()
    connection = open_database(config)
    with provider_client(config, connection) as client:
        observed = client.get_status(purpose="provider_capabilities")
    production = connection.execute(
        "SELECT provider_season, bool_or(provider_accessible) FROM competition_seasons "
        "WHERE ledger_mode='production' GROUP BY provider_season ORDER BY provider_season DESC LIMIT 1"
    ).fetchone()
    replay = connection.execute(
        "SELECT bool_or(provider_accessible) FROM competition_seasons WHERE ledger_mode='replay' AND provider_season=?",
        [config.provider_access.replay_season],
    ).fetchone()
    raw = connection.execute(
        "SELECT raw_path FROM api_request_log WHERE purpose='provider_capabilities' ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    payload = {
        "plan": observed.subscription_plan,
        "active": observed.subscription_active,
        "requests_current": observed.requests_used_today,
        "requests_limit_daily": observed.daily_limit,
        "daily_remaining": observed.daily_remaining,
        "minute_limit": observed.minute_limit,
        "minute_remaining": observed.minute_remaining,
        "production_season": production[0] if production else None,
        "production_access": "available" if production and production[1] else "blocked_or_unknown",
        "replay_season": config.provider_access.replay_season,
        "replay_access": "available" if replay and replay[0] else "not_audited_or_blocked",
    }
    connection.execute(
        "UPDATE provider_capabilities SET production_season=?, production_accessible=?, "
        "replay_season=?, replay_accessible=?, raw_path=coalesce(raw_path, ?) "
        "WHERE capability_id=(SELECT capability_id FROM provider_capabilities "
        "ORDER BY observed_at DESC LIMIT 1)",
        [
            payload["production_season"],
            bool(production and production[1]),
            payload["replay_season"],
            bool(replay and replay[0]),
            raw[0] if raw else None,
        ],
    )
    connection.close()
    if as_json:
        console.print_json(json.dumps(payload))
        return
    table = Table(title="API-Football Capabilities")
    table.add_column("Capability")
    table.add_column("State")
    for key, value in payload.items():
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)
