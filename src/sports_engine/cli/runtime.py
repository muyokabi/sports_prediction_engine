from collections.abc import Iterator
from contextlib import contextmanager

import duckdb

from sports_engine.core.config import AppConfig
from sports_engine.providers.api_football.auth import ApiFootballCredentials
from sports_engine.providers.api_football.client import ApiFootballClient
from sports_engine.quota.budget import QuotaBudget, QuotaPolicy
from sports_engine.quota.usage import latest
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.raw_store import RawStore


def open_database(config: AppConfig) -> duckdb.DuckDBPyConnection:
    connection = connect(config.database_path)
    migrate(connection)
    return connection


@contextmanager
def provider_client(config: AppConfig, connection: duckdb.DuckDBPyConnection) -> Iterator[ApiFootballClient]:
    credentials = ApiFootballCredentials.from_environment()
    budget = QuotaBudget(
        QuotaPolicy(config.quota.minimum_daily_reserve, config.quota.minimum_minute_reserve),
        latest(connection),
    )
    client = ApiFootballClient(
        credentials,
        RawStore(config.data_dir / "raw"),
        budget,
        connection,
        timeout_seconds=config.http.timeout_seconds,
        retry_count=config.http.retry_count,
        backoff_base_seconds=config.http.backoff_base_seconds,
    )
    try:
        yield client
    finally:
        client.close()
