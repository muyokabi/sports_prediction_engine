import duckdb

from sports_engine.providers.api_football.quota import QuotaObservation


def latest(connection: duckdb.DuckDBPyConnection) -> QuotaObservation | None:
    row = connection.execute(
        "SELECT requests_limit_daily, requests_remaining_daily, requests_limit_minute, "
        "requests_remaining_minute, completed_at FROM api_request_log "
        "WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    return QuotaObservation(*row) if row else None
