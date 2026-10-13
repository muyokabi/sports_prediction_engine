from dataclasses import dataclass

import duckdb

PRODUCTION_ACCESS_PROBE_LEAGUE = 39


@dataclass(frozen=True, slots=True)
class ProductionAccessProbe:
    league: int
    season: int
    stored_accessible: bool | None


def production_access_probe(
    connection: duckdb.DuckDBPyConnection,
    fallback_year: int,
) -> ProductionAccessProbe:
    """Resolve access evidence for the exact competition used by the probe.

    Provider catalogs legitimately contain future-dated tournament seasons. A
    global maximum season must never be paired with a different, hard-coded
    league because an empty response from that invalid pair says nothing about
    subscription access.
    """
    row = connection.execute(
        "SELECT cs.provider_season, cs.provider_accessible FROM competition_seasons cs "
        "JOIN provider_entity_map pem ON pem.canonical_entity_id=cs.competition_id "
        "WHERE pem.entity_type='competition' AND pem.provider_entity_id=? "
        "AND cs.ledger_mode='production' AND cs.admitted "
        "ORDER BY cs.provider_season DESC LIMIT 1",
        [str(PRODUCTION_ACCESS_PROBE_LEAGUE)],
    ).fetchone()
    if row:
        stored_accessible = None if row[1] is None else bool(row[1])
        return ProductionAccessProbe(PRODUCTION_ACCESS_PROBE_LEAGUE, int(row[0]), stored_accessible)
    return ProductionAccessProbe(PRODUCTION_ACCESS_PROBE_LEAGUE, fallback_year, None)
