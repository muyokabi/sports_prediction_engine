from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import duckdb


class MarketState(StrEnum):
    SUPPORTED = "SUPPORTED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    UNSUPPORTED_SETTLEMENT = "UNSUPPORTED_SETTLEMENT"
    NO_MODEL = "NO_MODEL"
    NO_ODDS = "NO_ODDS"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class CanonicalMarket:
    provider_market_id: int
    provider_name: str
    canonical_name: str
    family: str
    state: MarketState
    settlement_version: str | None


# These IDs and names are observed API-Football taxonomy, not inferred aliases.
API_FOOTBALL_MARKETS: dict[int, CanonicalMarket] = {
    1: CanonicalMarket(1, "Match Winner", "MATCH_ODDS", "SCORE", MarketState.SUPPORTED, "score-v1"),
    # Provider documentation does not unambiguously define draw settlement for
    # this two-way market. Keep it disabled until observed settlement is proven.
    2: CanonicalMarket(2, "Home/Away", "HOME_AWAY", "SCORE", MarketState.UNSUPPORTED_SETTLEMENT, None),
    4: CanonicalMarket(4, "Asian Handicap", "ASIAN_HANDICAP", "SCORE", MarketState.SUPPORTED, "asian-v1"),
    5: CanonicalMarket(5, "Goals Over/Under", "TOTAL_GOALS", "SCORE", MarketState.SUPPORTED, "asian-v1"),
    8: CanonicalMarket(8, "Both Teams Score", "BTTS", "SCORE", MarketState.SUPPORTED, "score-v1"),
    10: CanonicalMarket(10, "Exact Score", "CORRECT_SCORE", "SCORE", MarketState.SUPPORTED, "score-v1"),
    12: CanonicalMarket(12, "Double Chance", "DOUBLE_CHANCE", "SCORE", MarketState.SUPPORTED, "score-v1"),
    16: CanonicalMarket(16, "Total - Home", "HOME_TEAM_TOTAL", "SCORE", MarketState.SUPPORTED, "asian-v1"),
    17: CanonicalMarket(17, "Total - Away", "AWAY_TEAM_TOTAL", "SCORE", MarketState.SUPPORTED, "asian-v1"),
    45: CanonicalMarket(45, "Corners Over Under", "TOTAL_CORNERS", "CORNERS", MarketState.RESEARCH_ONLY, None),
    80: CanonicalMarket(80, "Cards Over/Under", "TOTAL_CARDS", "CARDS", MarketState.RESEARCH_ONLY, None),
    87: CanonicalMarket(87, "Total ShotOnGoal", "TOTAL_SHOTS_ON_TARGET", "SHOTS", MarketState.RESEARCH_ONLY, None),
    92: CanonicalMarket(92, "Anytime Goal Scorer", "ANYTIME_SCORER", "PLAYER", MarketState.RESEARCH_ONLY, None),
}

DOUBLE_CHANCE_SELECTIONS = {
    "HOME OR DRAW": "HOME/DRAW",
    "HOME/DRAW": "HOME/DRAW",
    "1X": "HOME/DRAW",
    "HOME OR AWAY": "HOME/AWAY",
    "HOME/AWAY": "HOME/AWAY",
    "12": "HOME/AWAY",
    "DRAW OR AWAY": "DRAW/AWAY",
    "DRAW/AWAY": "DRAW/AWAY",
    "X2": "DRAW/AWAY",
}


def canonical_selection(canonical_market: str, provider_selection: str) -> str:
    normalized = " ".join(provider_selection.upper().split())
    if canonical_market == "DOUBLE_CHANCE":
        return DOUBLE_CHANCE_SELECTIONS.get(normalized, normalized)
    return normalized


def classify_api_football_market(provider_market_id: int, provider_name: str) -> CanonicalMarket:
    market = API_FOOTBALL_MARKETS.get(provider_market_id)
    if market is None:
        return CanonicalMarket(
            provider_market_id,
            provider_name,
            f"UNKNOWN_API_FOOTBALL_{provider_market_id}",
            "UNKNOWN",
            MarketState.UNSUPPORTED_SETTLEMENT,
            None,
        )
    if market.provider_name.casefold() != provider_name.strip().casefold():
        return CanonicalMarket(
            provider_market_id,
            provider_name,
            market.canonical_name,
            market.family,
            MarketState.DISABLED,
            None,
        )
    return market


def persist_observed_api_football_markets(connection: duckdb.DuckDBPyConnection) -> int:
    observed = connection.execute("SELECT provider_market_id, name FROM bet_markets").fetchall()
    now = datetime.now(UTC)
    rows = []
    for provider_market_id, provider_name in observed:
        market = classify_api_football_market(int(provider_market_id), str(provider_name))
        rows.append(
            [
                "api_football",
                market.provider_market_id,
                market.provider_name,
                market.canonical_name,
                market.family,
                market.state,
                market.settlement_version,
                now,
                now,
            ]
        )
    if rows:
        connection.executemany(
            "INSERT INTO canonical_market_mappings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (provider, provider_market_id) DO UPDATE SET "
            "provider_market_name=excluded.provider_market_name, canonical_market=excluded.canonical_market, "
            "market_family=excluded.market_family, state=excluded.state, "
            "settlement_version=excluded.settlement_version, last_seen_at=excluded.last_seen_at",
            rows,
        )
    return len(rows)
