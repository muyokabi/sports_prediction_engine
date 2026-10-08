import hashlib
import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import duckdb

from sports_engine.core.ids import canonical_id
from sports_engine.markets.implied_probability import no_vig_probabilities, raw_implied_probability
from sports_engine.markets.overround import overround
from sports_engine.markets.taxonomy import persist_observed_api_football_markets
from sports_engine.sports.football.domain.odds import OddsPrice


def store_odds_snapshot(
    connection: duckdb.DuckDBPyConnection,
    prices: list[OddsPrice],
    *,
    source_raw_path: str,
    job_run_id: str | None,
    observed_at: datetime | None = None,
    dedupe_seconds: int = 60,
) -> bool:
    if not prices:
        return False
    observed = observed_at or datetime.now(UTC)
    provider_fixture_id = prices[0].provider_fixture_id
    if any(price.provider_fixture_id != provider_fixture_id for price in prices):
        raise ValueError("An odds snapshot must contain exactly one fixture")
    fixture = connection.execute(
        "SELECT CAST(fixture_id AS VARCHAR) FROM fixtures WHERE provider_fixture_id=?",
        [provider_fixture_id],
    ).fetchone()
    if fixture is None:
        return False
    fixture_id = fixture[0]
    canonical = sorted(
        (price.model_dump(mode="json") for price in prices),
        key=lambda item: (
            item["provider_bookmaker_id"],
            item["provider_market_id"],
            item["selection_name"],
            item["line"] or "",
        ),
    )
    content_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    latest = connection.execute(
        "SELECT observed_at, content_hash FROM odds_snapshots WHERE fixture_id=? ORDER BY observed_at DESC LIMIT 1",
        [fixture_id],
    ).fetchone()
    if latest and latest[1] == content_hash and observed - latest[0] <= timedelta(seconds=dedupe_seconds):
        return False
    snapshot_id = uuid.uuid5(
        canonical_id("odds_snapshot", "api_football", provider_fixture_id),
        f"{observed.isoformat()}:{content_hash}",
    )
    provider_update = max(
        (price.provider_update_time for price in prices if price.provider_update_time is not None),
        default=None,
    )
    connection.execute(
        "INSERT INTO odds_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
        [snapshot_id, fixture_id, observed, provider_update, source_raw_path, job_run_id, content_hash],
    )
    groups: dict[tuple[int, int], list[OddsPrice]] = defaultdict(list)
    for price in prices:
        groups[(price.provider_bookmaker_id, price.provider_market_id)].append(price)
    bookmakers: dict[object, list[object]] = {}
    markets: dict[object, list[object]] = {}
    selections: dict[object, list[object]] = {}
    price_rows: dict[tuple[object, object, object, object], list[object]] = {}
    for group in groups.values():
        decimal = [price.decimal_odds for price in group]
        fair: list[float | None] = (
            [float(value) for value in no_vig_probabilities(decimal)] if len(decimal) >= 2 else [None] * len(decimal)
        )
        margin = overround(decimal) if len(decimal) >= 2 else None
        for index, price in enumerate(group):
            bookmaker_id = canonical_id("bookmaker", "api_football", price.provider_bookmaker_id)
            market_id = canonical_id("market", "api_football", price.provider_market_id)
            normalized = " ".join(price.selection_name.lower().split())
            selection_id = canonical_id(
                "selection", "api_football", f"{price.provider_market_id}:{normalized}:{price.line or ''}"
            )
            bookmakers[bookmaker_id] = [bookmaker_id, price.provider_bookmaker_id, price.bookmaker_name]
            markets[market_id] = [market_id, price.provider_market_id, price.market_name]
            selections[selection_id] = [selection_id, market_id, price.selection_name, normalized, price.line]
            key = (snapshot_id, bookmaker_id, market_id, selection_id)
            price_rows[key] = [
                *key,
                price.decimal_odds,
                raw_implied_probability(price.decimal_odds),
                fair[index],
                margin,
            ]
    connection.executemany(
        "INSERT INTO bookmakers VALUES (?, ?, ?) ON CONFLICT (bookmaker_id) DO UPDATE SET name=excluded.name",
        list(bookmakers.values()),
    )
    connection.executemany(
        "INSERT INTO bet_markets VALUES (?, ?, ?) ON CONFLICT (market_id) DO UPDATE SET name=excluded.name",
        list(markets.values()),
    )
    persist_observed_api_football_markets(connection)
    connection.executemany(
        "INSERT INTO bet_selections VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        list(selections.values()),
    )
    connection.executemany(
        "INSERT INTO odds_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        list(price_rows.values()),
    )
    return True
