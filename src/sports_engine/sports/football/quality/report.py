from dataclasses import dataclass

import duckdb


@dataclass(frozen=True, slots=True)
class CompetitionQualitySummary:
    competition: str
    season: int
    ledger_mode: str
    total: int
    completed: int
    enriched: int
    ml_eligible: int
    pending_repair: int
    quarantined: int
    unavailable_components: int
    completeness_percentage: float
    common_missing: tuple[tuple[str, int], ...]


def quality_summary(connection: duckdb.DuckDBPyConnection) -> list[CompetitionQualitySummary]:
    rows = connection.execute(
        "SELECT c.name, cs.provider_season, cs.ledger_mode, count(DISTINCT f.fixture_id), "
        "count(DISTINCT f.fixture_id) FILTER (WHERE f.status_short IN ('FT','AET','PEN')), "
        "count(DISTINCT q.fixture_id), "
        "count(DISTINCT f.fixture_id) FILTER (WHERE q.eligibility='ML_ELIGIBLE'), "
        "count(DISTINCT f.fixture_id) FILTER (WHERE coalesce(q.eligibility, f.eligibility)='PENDING_REPAIR'), "
        "count(DISTINCT d.fixture_id), count(*) FILTER (WHERE fc.state='unavailable') "
        "FROM competition_seasons cs JOIN competitions c USING (competition_id) "
        "LEFT JOIN fixtures_current f USING (competition_season_id) "
        "LEFT JOIN fixture_quality_status q USING (fixture_id) "
        "LEFT JOIN data_quality_issues d ON d.fixture_id=f.fixture_id AND d.resolved_at IS NULL "
        "LEFT JOIN fixture_completeness fc USING (fixture_id) "
        "GROUP BY c.name, cs.provider_season, cs.ledger_mode "
        "ORDER BY cs.ledger_mode, c.name, cs.provider_season"
    ).fetchall()
    result = []
    for row in rows:
        missing = connection.execute(
            "SELECT fc.component, count(*) FROM fixture_completeness fc "
            "JOIN fixtures f USING (fixture_id) JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) "
            "WHERE c.name=? AND cs.provider_season=? AND cs.ledger_mode=? AND fc.state<>'complete' "
            "GROUP BY fc.component ORDER BY count(*) DESC, fc.component LIMIT 5",
            [row[0], row[1], row[2]],
        ).fetchall()
        completed = int(row[4])
        eligible = int(row[6])
        result.append(
            CompetitionQualitySummary(
                str(row[0]),
                int(row[1]),
                str(row[2]),
                int(row[3]),
                completed,
                int(row[5]),
                eligible,
                int(row[7]),
                int(row[8]),
                int(row[9]),
                100.0 * eligible / completed if completed else 0.0,
                tuple((str(name), int(count)) for name, count in missing),
            )
        )
    return result


def quality_details(connection: duckdb.DuckDBPyConnection) -> list[tuple[str, int, str, str, str]]:
    return connection.execute(
        "SELECT c.name, cs.provider_season, CAST(f.fixture_id AS VARCHAR), fc.component, fc.state "
        "FROM fixture_completeness fc JOIN fixtures f USING (fixture_id) "
        "JOIN competition_seasons cs USING (competition_season_id) "
        "JOIN competitions c USING (competition_id) WHERE fc.state<>'complete' "
        "ORDER BY c.name, cs.provider_season, f.kickoff_utc, fc.component"
    ).fetchall()
