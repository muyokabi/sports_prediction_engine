import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean, median

import duckdb
import numpy as np


@dataclass(frozen=True, slots=True)
class OddsAgeResearchResult:
    observations: int
    scopes_written: int


def refresh_odds_age_research(
    connection: duckdb.DuckDBPyConnection,
    *,
    computed_at: datetime | None = None,
    minimum_scope_sample: int = 5,
) -> OddsAgeResearchResult:
    """Measure quote-age/movement relationships without activating a production penalty."""
    now = computed_at or datetime.now(UTC)
    rows = connection.execute(
        "WITH priced AS (SELECT o.snapshot_id, o.fixture_id, o.observed_at, o.provider_update_time, "
        "p.bookmaker_id, p.market_id, p.selection_id, p.decimal_odds, "
        "p.raw_implied_probability / sum(p.raw_implied_probability) OVER "
        "(PARTITION BY o.snapshot_id, p.bookmaker_id, p.market_id, coalesce(s.line, '')) fair_probability "
        "FROM odds_snapshots o JOIN odds_prices p USING (snapshot_id) JOIN bet_selections s USING (selection_id)) "
        "SELECT CAST(o.fixture_id AS VARCHAR), c.name, cm.canonical_market, b.name, "
        "CAST(b.bookmaker_id AS VARCHAR), CAST(m.market_id AS VARCHAR), CAST(s.selection_id AS VARCHAR), "
        "coalesce(s.line, ''), f.kickoff_utc, coalesce(o.provider_update_time, o.observed_at), "
        "o.fair_probability, o.decimal_odds FROM priced o JOIN fixtures_current f USING (fixture_id) "
        "JOIN competition_seasons cs USING (competition_season_id) "
        "JOIN competitions c USING (competition_id) JOIN bookmakers b USING (bookmaker_id) "
        "JOIN bet_markets m USING (market_id) JOIN bet_selections s USING (selection_id) "
        "JOIN canonical_market_mappings cm ON cm.provider='api_football' "
        "AND cm.provider_market_id=m.provider_market_id WHERE f.status_short IN ('FT','AET','PEN') "
        "AND cm.state='SUPPORTED' AND coalesce(o.provider_update_time, o.observed_at)<f.kickoff_utc "
        "AND o.fair_probability IS NOT NULL ORDER BY o.fixture_id, b.bookmaker_id, m.market_id, "
        "s.selection_id, coalesce(s.line, ''), coalesce(o.provider_update_time, o.observed_at)",
    ).fetchall()
    series: dict[tuple[str, str, str, str, str], list[tuple[datetime, datetime, float, float]]] = defaultdict(list)
    labels: dict[tuple[str, str, str, str, str], tuple[str, str, str]] = {}
    for row in rows:
        key = (str(row[0]), str(row[4]), str(row[5]), str(row[6]), str(row[7]))
        series[key].append((row[8], row[9], float(row[10]), float(row[11])))
        labels[key] = (str(row[1]), str(row[2]), str(row[3]))
    observations: list[tuple[str, str, str, float, float, float]] = []
    for key, values in series.items():
        if len(values) < 2:
            continue
        kickoff, _, final_probability, _ = values[-1]
        league, market, bookmaker = labels[key]
        for _, observed, probability, _ in values[:-1]:
            age_minutes = max(0.0, (kickoff - observed).total_seconds() / 60)
            movement = abs(final_probability - probability)
            observations.append((league, market, bookmaker, age_minutes, movement, 0.0))
    scopes: dict[tuple[str, str, str], list[tuple[float, float, float]]] = defaultdict(list)
    for league, market, bookmaker, age, movement, dispersion in observations:
        scopes[("GLOBAL", "ALL", market)].append((age, movement, dispersion))
        scopes[("COMPETITION", league, market)].append((age, movement, dispersion))
        scopes[("BOOKMAKER", bookmaker, market)].append((age, movement, dispersion))
    written = 0
    for (scope_type, scope_key, market), scope_values in scopes.items():
        if scope_type != "GLOBAL" and len(scope_values) < minimum_scope_sample:
            continue
        ages = np.asarray([value[0] for value in scope_values], dtype=float)
        movements = np.asarray([value[1] for value in scope_values], dtype=float)
        correlation = (
            float(np.corrcoef(ages, movements)[0, 1])
            if len(scope_values) >= 3 and float(np.std(ages)) > 0 and float(np.std(movements)) > 0
            else None
        )
        evidence = {
            "method": "earlier-fair-probability-vs-final-observed-pre-kickoff-v1",
            "penalty_status": "RESEARCH_ONLY",
            "minimum_scope_sample": minimum_scope_sample,
        }
        connection.execute(
            "INSERT INTO odds_age_research_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, false, ?, ?)",
            [
                str(uuid.uuid4()),
                scope_type,
                scope_key,
                market,
                len(scope_values),
                float(median(ages)),
                float(mean(movements)),
                float(median(movements)),
                float(mean(value[2] for value in scope_values)),
                correlation,
                json.dumps(evidence, sort_keys=True),
                now,
            ],
        )
        written += 1
    return OddsAgeResearchResult(len(observations), written)
