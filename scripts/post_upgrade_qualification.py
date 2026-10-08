"""Controlled, raw-first API-Football paid-plan qualification."""

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sports_engine.cli.runtime import open_database, provider_client
from sports_engine.core.config import load_config
from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.endpoints import Endpoint

LEAGUES = ((39, "Premier League"), (140, "La Liga"), (135, "Serie A"), (78, "Bundesliga"), (61, "Ligue 1"))
FIELDS = {
    "minutes": ("games", "minutes"),
    "rating": ("games", "rating"),
    "shots.total": ("shots", "total"),
    "shots.on": ("shots", "on"),
    "passes.total": ("passes", "total"),
    "passes.key": ("passes", "key"),
    "passes.accuracy": ("passes", "accuracy"),
    "tackles.total": ("tackles", "total"),
    "interceptions": ("tackles", "interceptions"),
    "duels.total": ("duels", "total"),
    "duels.won": ("duels", "won"),
    "dribbles.attempts": ("dribbles", "attempts"),
    "dribbles.success": ("dribbles", "success"),
    "fouls.drawn": ("fouls", "drawn"),
    "fouls.committed": ("fouls", "committed"),
    "cards.yellow": ("cards", "yellow"),
    "cards.red": ("cards", "red"),
}
ROLE_EVENT_FIELDS = {
    "goals.saves": ("goals", "saves"),
    "penalty.saved": ("penalty", "saved"),
    "penalty.won": ("penalty", "won"),
    "penalty.committed": ("penalty", "commited"),
    "goals.assists": ("goals", "assists"),
    "goals.total": ("goals", "total"),
    "dribbles.past": ("dribbles", "past"),
}


def nested(row: dict[str, Any], path: tuple[str, str]) -> Any:
    section = row.get(path[0])
    return section.get(path[1]) if isinstance(section, dict) else None


def participation(player_id: int, stats: dict[str, Any], starters: set[int], substitutes: set[int]) -> str:
    minutes = nested(stats, ("games", "minutes"))
    appeared = isinstance(minutes, (int, float)) and minutes > 0
    if player_id in starters or (appeared and nested(stats, ("games", "substitute")) is False):
        return "STARTED_AND_PLAYED" if appeared else "OTHER_UNKNOWN"
    if player_id in substitutes:
        return "SUBSTITUTE_APPEARED" if appeared else "UNUSED_SUBSTITUTE"
    if appeared:
        return "SUBSTITUTE_APPEARED" if nested(stats, ("games", "substitute")) else "OTHER_UNKNOWN"
    return "UNUSED_SUBSTITUTE" if nested(stats, ("games", "substitute")) else "OTHER_UNKNOWN"


def component_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fixtures": len(rows),
        "events": sum(isinstance(row.get("events"), list) for row in rows),
        "lineups": sum(isinstance(row.get("lineups"), list) and len(row["lineups"]) >= 2 for row in rows),
        "team_statistics": sum(isinstance(row.get("statistics"), list) and len(row["statistics"]) >= 2 for row in rows),
        "player_statistics": sum(isinstance(row.get("players"), list) and len(row["players"]) >= 2 for row in rows),
    }


def player_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    nulls: dict[str, Counter[str]] = defaultdict(Counter)
    for fixture in rows:
        starters: set[int] = set()
        substitutes: set[int] = set()
        for lineup in fixture.get("lineups") or []:
            starters.update(int(item["player"]["id"]) for item in lineup.get("startXI") or [])
            substitutes.update(int(item["player"]["id"]) for item in lineup.get("substitutes") or [])
        for team in fixture.get("players") or []:
            for player in team.get("players") or []:
                statistics = player.get("statistics") or []
                stats = statistics[0] if statistics else {}
                group = participation(int(player["player"]["id"]), stats, starters, substitutes)
                totals[group] += 1
                for name, path in {**FIELDS, **ROLE_EVENT_FIELDS}.items():
                    if nested(stats, path) is None:
                        nulls[group][name] += 1
    return {
        group: {
            "players": count,
            "fields": {
                field: {
                    "null": nulls[group][field],
                    "available": count - nulls[group][field],
                    "null_rate": round(nulls[group][field] / count, 4) if count else None,
                }
                for field in (*FIELDS, *ROLE_EVENT_FIELDS)
            },
        }
        for group, count in totals.items()
    }


def main() -> None:
    config = load_config()
    connection = open_database(config)
    output: dict[str, Any] = {"season": date.today().year}
    try:
        with provider_client(config, connection) as client:
            status = client.get_status(purpose="post_upgrade_qualification_status")
            output["capabilities"] = status.model_dump(mode="json")
            discovered: dict[str, list[dict[str, Any]]] = {}
            for league_id, name in LEAGUES:
                discovered[name] = client.get(
                    Endpoint.FIXTURES,
                    {"league": league_id, "season": output["season"], "status": "FT"},
                    purpose=f"post_upgrade_completed:{league_id}:{output['season']}",
                    priority=Priority.P1,
                )
            output["completed_discovery"] = {name: len(rows) for name, rows in discovered.items()}
            premier_ids = [int(row["fixture"]["id"]) for row in discovered["Premier League"]]
            sample_ids = [
                int(row["fixture"]["id"])
                for name, _ in ((name, rows) for name, rows in discovered.items())
                for row in sorted(discovered[name], key=lambda item: item["fixture"]["date"], reverse=True)[:4]
            ]
            batch_results = []
            batch_payloads: list[dict[str, Any]] = []
            for size, ids in ((2, premier_ids[:2]), (10, premier_ids[:10]), (20, sample_ids[:20])):
                before = client.capabilities.daily_remaining if client.capabilities else None
                rows = client.get(
                    Endpoint.FIXTURES,
                    {"ids": "-".join(map(str, ids))},
                    purpose=f"post_upgrade_multi_id:{size}",
                    priority=Priority.P1,
                )
                after = client.capabilities.daily_remaining if client.capabilities else None
                batch_results.append(
                    {
                        "ids_requested": len(ids),
                        "results_returned": len(rows),
                        "requests_consumed": before - after if before is not None and after is not None else None,
                        "components": component_summary(rows),
                    }
                )
                if size == 20:
                    batch_payloads = rows
            output["multi_id_batches"] = batch_results
            output["sample_fixture_ids"] = [int(row["fixture"]["id"]) for row in batch_payloads]
            output["sample_competitions"] = Counter(str(row["league"]["name"]) for row in batch_payloads)
            output["sample_components"] = component_summary(batch_payloads)
            output["player_null_matrix"] = player_matrix(batch_payloads)

            target = date.today() + timedelta(days=1)
            odds_rows: list[dict[str, Any]] = []
            first = client.get_envelope(
                Endpoint.ODDS,
                {"date": target.isoformat(), "page": 1},
                purpose=f"post_upgrade_odds:{target}:page:1",
                priority=Priority.P2,
            )
            odds_rows.extend(first.response)
            for page in range(2, first.paging.total + 1):
                envelope = client.get_envelope(
                    Endpoint.ODDS,
                    {"date": target.isoformat(), "page": page},
                    purpose=f"post_upgrade_odds:{target}:page:{page}",
                    priority=Priority.P2,
                )
                odds_rows.extend(envelope.response)
            bookmaker_ids = {book["id"] for row in odds_rows for book in row.get("bookmakers") or []}
            markets = [
                bet for row in odds_rows for book in row.get("bookmakers") or [] for bet in book.get("bets") or []
            ]
            selections = [value for bet in markets for value in bet.get("values") or []]
            output["odds"] = {
                "date": target.isoformat(),
                "paging_total": first.paging.total,
                "fixtures": len(odds_rows),
                "bookmakers": len(bookmaker_ids),
                "markets": len(markets),
                "selections": len(selections),
                "decimal_odds_valid": sum(float(value["odd"]) > 1 for value in selections),
                "lines_or_handicaps": sum(
                    any(char.isdigit() for char in str(value.get("value", ""))) for value in selections
                ),
                "provider_updates": sum(row.get("update") is not None for row in odds_rows),
            }
            output["final_capabilities"] = client.capabilities.model_dump(mode="json") if client.capabilities else None
    finally:
        connection.close()
    path = Path("artifacts/reports/post-upgrade-provider-qualification.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
