"""Emit a read-only, machine-readable warehouse audit snapshot."""

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb


def _rows(connection: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    cursor = connection.execute(query)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def audit(path: Path) -> dict[str, Any]:
    connection = duckdb.connect(str(path), read_only=True)
    try:
        counts = _rows(
            connection,
            "SELECT "
            "(SELECT count(*) FROM competitions) competitions, "
            "(SELECT count(*) FROM competition_seasons) competition_seasons, "
            "(SELECT count(*) FROM teams) teams, "
            "(SELECT count(*) FROM fixtures_current) fixtures, "
            "(SELECT count(*) FROM fixtures_current WHERE status_short IN ('FT','AET','PEN')) completed, "
            "(SELECT count(*) FROM fixture_quality_status) quality_assessed, "
            "(SELECT count(*) FROM fixture_quality_status WHERE eligibility='ML_ELIGIBLE') ml_eligible, "
            "(SELECT count(DISTINCT fixture_id) FROM fixture_repair_state) repair_tracked, "
            "(SELECT count(*) FROM odds_snapshots) odds_snapshots, "
            "(SELECT count(*) FROM odds_prices) odds_prices, "
            "(SELECT count(DISTINCT fixture_id) FROM odds_snapshots) fixtures_with_odds, "
            "(SELECT count(*) FROM bookmakers) bookmakers, "
            "(SELECT count(*) FROM bet_markets) provider_markets, "
            "(SELECT count(*) FROM feature_datasets) feature_datasets, "
            "(SELECT count(*) FROM model_runs) model_runs, "
            "(SELECT count(*) FROM predictions) legacy_predictions, "
            "(SELECT count(*) FROM institutional_predictions) institutional_predictions, "
            "(SELECT count(*) FROM institutional_opportunities) institutional_opportunities, "
            "(SELECT count(*) FROM shadow_opportunities) shadow_opportunities, "
            "(SELECT count(*) FROM shadow_opportunities WHERE settled_at IS NOT NULL) settled_shadow",
        )[0]
        latest_backfill = _rows(
            connection,
            "SELECT job_run_id, started_at, finished_at, status, metrics "
            "FROM job_runs WHERE job_name LIKE 'football.fetch_backfill.%' "
            "ORDER BY started_at DESC LIMIT 1",
        )
        latest_backfill_id = str(latest_backfill[0]["job_run_id"]) if latest_backfill else None
        return {
            "database": str(path.resolve()),
            "counts": counts,
            "competition_states": _rows(
                connection,
                "SELECT universe_state state, count(*) count FROM competition_discoveries GROUP BY 1 ORDER BY 1",
            ),
            "ledger_coverage": _rows(
                connection,
                "SELECT cs.ledger_mode, count(DISTINCT cs.competition_season_id) competition_seasons, "
                "count(DISTINCT f.fixture_id) fixtures, "
                "count(DISTINCT f.fixture_id) FILTER (WHERE f.status_short IN ('FT','AET','PEN')) completed, "
                "count(DISTINCT q.fixture_id) FILTER (WHERE q.eligibility='ML_ELIGIBLE') ml_eligible, "
                "count(DISTINCT o.fixture_id) fixtures_with_odds "
                "FROM competition_seasons cs LEFT JOIN fixtures_current f USING (competition_season_id) "
                "LEFT JOIN fixture_quality_status q USING (fixture_id) "
                "LEFT JOIN odds_snapshots o USING (fixture_id) GROUP BY 1 ORDER BY 1",
            ),
            "quality_states": _rows(
                connection,
                "SELECT eligibility, count(*) count FROM fixture_quality_status GROUP BY 1 ORDER BY 2 DESC",
            ),
            "component_states": _rows(
                connection,
                "SELECT component, state, count(*) count FROM fixture_completeness GROUP BY 1,2 ORDER BY 1,2",
            ),
            "repair_missing_combinations": _rows(
                connection,
                "SELECT CAST(last_missing AS VARCHAR) missing, count(*) fixtures "
                "FROM fixture_repair_state GROUP BY 1 ORDER BY 2 DESC, 1",
            ),
            "replay_competition_coverage": _rows(
                connection,
                "SELECT CAST(pem.provider_entity_id AS BIGINT) provider_competition_id, "
                "c.name, c.country, count(DISTINCT cs.provider_season) registered_seasons, "
                "count(DISTINCT f.fixture_id) fixtures, "
                "count(DISTINCT f.fixture_id) FILTER (WHERE f.status_short IN ('FT','AET','PEN')) completed, "
                "count(DISTINCT q.fixture_id) assessed, "
                "count(DISTINCT q.fixture_id) FILTER (WHERE q.eligibility='ML_ELIGIBLE') ml_eligible, "
                "count(DISTINCT q.fixture_id) FILTER (WHERE q.eligibility='PENDING_REPAIR') pending_repair, "
                "count(DISTINCT f.fixture_id) FILTER (WHERE f.status_short IN ('FT','AET','PEN') "
                "AND q.fixture_id IS NULL) unassessed_completed, min(f.kickoff_utc) first_fixture, "
                "max(f.kickoff_utc) last_fixture "
                "FROM competition_seasons cs JOIN competitions c USING (competition_id) "
                "JOIN provider_entity_map pem ON pem.canonical_entity_id=c.competition_id "
                "AND pem.entity_type='competition' LEFT JOIN fixtures_current f USING (competition_season_id) "
                "LEFT JOIN fixture_quality_status q USING (fixture_id) "
                "WHERE cs.ledger_mode='replay' AND cs.replay_eligible "
                "GROUP BY 1,2,3 ORDER BY ml_eligible DESC, c.name",
            ),
            "latest_backfill": latest_backfill[0] if latest_backfill else None,
            "latest_backfill_requests": (
                _rows(
                    connection,
                    "SELECT endpoint, split_part(purpose, ':', 1) purpose_group, count(*) requests, "
                    "sum(coalesce(response_results, 0)) response_results, "
                    "min(requests_remaining_daily) minimum_daily_remaining "
                    f"FROM api_request_log WHERE CAST(job_run_id AS VARCHAR)='{latest_backfill_id}' "
                    "GROUP BY 1,2 ORDER BY requests DESC, endpoint, purpose_group",
                )
                if latest_backfill_id is not None
                else []
            ),
            "feature_datasets": _rows(
                connection,
                "SELECT name, created_at, feature_cutoff_start, feature_cutoff_end, "
                "dataset_hash, parquet_path, config "
                "FROM feature_datasets ORDER BY created_at DESC",
            ),
            "repair_attempts": _rows(
                connection,
                "SELECT attempt_count, count(*) fixtures FROM fixture_repair_state GROUP BY 1 ORDER BY 1",
            ),
            "models": _rows(
                connection,
                "SELECT model_type, version, status, coalesce(evidence_state, 'UNASSESSED') evidence_state, "
                "training_cutoff, observations_included, calibration_method, artifact_path "
                "FROM model_runs ORDER BY created_at DESC",
            ),
            "market_roles": _rows(
                connection,
                "SELECT market_family, role_name, model_version, state, selected_at "
                "FROM model_market_roles ORDER BY selected_at DESC",
            ),
            "probability_scopes": _rows(
                connection,
                "SELECT market_family, scope_type, state, count(*) count "
                "FROM model_probability_scope_validations GROUP BY 1,2,3 ORDER BY 1,2,3",
            ),
            "applicability": _rows(
                connection,
                "SELECT applicability_state, actionability_qualified, count(*) count "
                "FROM prediction_applicability GROUP BY 1,2 ORDER BY 1,2",
            ),
            "opportunity_funnel": _rows(
                connection,
                "SELECT governance_state, decision, count(*) count FROM institutional_opportunities "
                "GROUP BY 1,2 ORDER BY 1,2",
            ),
            "duplicate_prediction_clusters": _rows(
                connection,
                "SELECT count(*) clusters, coalesce(sum(copies), 0) rows_in_clusters FROM ("
                "SELECT count(*) copies FROM prediction_applicability GROUP BY probabilities, "
                "expected_home_goals, expected_away_goals HAVING count(*)>1)",
            )[0],
            "recent_jobs": _rows(
                connection,
                "SELECT job_name, started_at, finished_at, status, error_category, error_message, metrics "
                "FROM job_runs ORDER BY started_at DESC LIMIT 10",
            ),
            "recent_analyses": _rows(
                connection,
                "SELECT analysis_run_id, requested_start_date, requested_end_date, analysis_timestamp, state, "
                "expected_fixture_count, terminal_fixture_count, report_mode, report_path "
                "FROM analysis_runs ORDER BY analysis_timestamp DESC LIMIT 10",
            ),
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", nargs="?", type=Path, default=Path("data/warehouse/sports.duckdb"))
    args = parser.parse_args()
    print(json.dumps(audit(args.database), indent=2, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
