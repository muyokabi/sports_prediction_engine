import duckdb


def latest_raw_path(connection: duckdb.DuckDBPyConnection, purpose: str, job_run_id: str | None = None) -> str:
    if job_run_id:
        row = connection.execute(
            "SELECT raw_path FROM api_request_log WHERE purpose=? AND job_run_id=? "
            "AND raw_path IS NOT NULL ORDER BY completed_at DESC LIMIT 1",
            [purpose, job_run_id],
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT raw_path FROM api_request_log WHERE purpose=? AND raw_path IS NOT NULL "
            "ORDER BY completed_at DESC LIMIT 1",
            [purpose],
        ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"No raw lineage path recorded for purpose {purpose!r}")
    return str(row[0])
