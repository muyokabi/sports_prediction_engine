import hashlib
import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import duckdb
import polars as pl

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
    provider_update = max(
        (price.provider_update_time for price in prices if price.provider_update_time is not None),
        default=None,
    )
    latest = connection.execute(
        "SELECT observed_at, content_hash, provider_update_time FROM odds_snapshots "
        "WHERE fixture_id=? ORDER BY observed_at DESC LIMIT 1",
        [fixture_id],
    ).fetchone()
    if latest and latest[1] == content_hash:
        within_collection_window = observed - latest[0] <= timedelta(seconds=dedupe_seconds)
        unchanged_provider_observation = provider_update is not None and provider_update == latest[2]
        if within_collection_window or unchanged_provider_observation:
            return False
    snapshot_id = uuid.uuid5(
        canonical_id("odds_snapshot", "api_football", provider_fixture_id),
        f"{observed.isoformat()}:{content_hash}",
    )
    connection.execute(
        "INSERT INTO odds_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
        [snapshot_id, fixture_id, observed, provider_update, source_raw_path, job_run_id, content_hash],
    )
    groups: dict[tuple[int, int, str], list[OddsPrice]] = defaultdict(list)
    for price in prices:
        line_group = price.line or ""
        if line_group and "handicap" in price.market_name.casefold():
            line_group = f"{abs(float(line_group)):g}"
        groups[(price.provider_bookmaker_id, price.provider_market_id, line_group)].append(price)
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
    _bulk_insert(
        connection,
        "_incoming_bookmakers",
        ["bookmaker_id", "provider_bookmaker_id", "name"],
        [[str(row[0]), row[1], row[2]] for row in bookmakers.values()],
        "INSERT INTO bookmakers SELECT * FROM _incoming_bookmakers "
        "ON CONFLICT (bookmaker_id) DO UPDATE SET name=excluded.name",
    )
    _bulk_insert(
        connection,
        "_incoming_markets",
        ["market_id", "provider_market_id", "name"],
        [[str(row[0]), row[1], row[2]] for row in markets.values()],
        "INSERT INTO bet_markets SELECT * FROM _incoming_markets "
        "ON CONFLICT (market_id) DO UPDATE SET name=excluded.name",
    )
    persist_observed_api_football_markets(connection)
    _bulk_insert(
        connection,
        "_incoming_selections",
        ["selection_id", "market_id", "name", "normalized_name", "line"],
        [[str(row[0]), str(row[1]), row[2], row[3], row[4]] for row in selections.values()],
        "INSERT INTO bet_selections SELECT * FROM _incoming_selections ON CONFLICT DO NOTHING",
    )
    _bulk_insert(
        connection,
        "_incoming_prices",
        [
            "snapshot_id",
            "bookmaker_id",
            "market_id",
            "selection_id",
            "decimal_odds",
            "raw_implied_probability",
            "fair_probability",
            "overround",
        ],
        [[str(row[0]), str(row[1]), str(row[2]), str(row[3]), *row[4:]] for row in price_rows.values()],
        "INSERT INTO odds_prices SELECT * FROM _incoming_prices",
    )
    return True


def _bulk_insert(
    connection: duckdb.DuckDBPyConnection,
    relation_name: str,
    columns: list[str],
    rows: list[list[object]],
    statement: str,
) -> None:
    """Insert provider-sized batches through DuckDB's columnar scan path.

    DuckDB's Python ``executemany`` executes once per row and made a normal
    API-Football odds page take minutes when a fixture carried thousands of
    prices. Registering a typed frame preserves the surrounding transaction
    while turning the write into one set-based statement.
    """
    if not rows:
        return
    frame = pl.DataFrame(rows, schema=columns, orient="row", infer_schema_length=None)
    connection.register(relation_name, frame)
    try:
        connection.execute(statement)
    finally:
        connection.unregister(relation_name)
