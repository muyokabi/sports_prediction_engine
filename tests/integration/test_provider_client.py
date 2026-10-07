from pathlib import Path

import httpx

from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.auth import ApiFootballCredentials
from sports_engine.providers.api_football.client import ApiFootballClient
from sports_engine.quota.budget import QuotaBudget, QuotaPolicy
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.raw_store import RawStore


def test_provider_client_validates_logs_and_preserves_raw(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-apisports-key"] == "secret"
        return httpx.Response(
            200,
            headers={
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "99",
                "x-ratelimit-limit": "10",
                "x-ratelimit-remaining": "9",
            },
            json={
                "get": "fixtures",
                "parameters": {"date": "2026-01-01"},
                "errors": [],
                "results": 1,
                "paging": {"current": 1, "total": 1},
                "response": [{"fixture": {"id": 1}}],
            },
        )

    connection = connect(tmp_path / "test.duckdb")
    migrate(connection)
    client = ApiFootballClient(
        ApiFootballCredentials("secret", "https://example.test"),
        RawStore(tmp_path / "raw"),
        QuotaBudget(QuotaPolicy(10, 2)),
        connection,
        transport=httpx.MockTransport(handler),
    )
    result = client.get(
        "/fixtures",
        {"date": "2026-01-01"},
        purpose="provider_contract",
        priority=Priority.P1,
    )
    client.close()
    assert result == [{"fixture": {"id": 1}}]
    request = connection.execute(
        "SELECT http_status, response_results, requests_remaining_daily, raw_path FROM api_request_log"
    ).fetchone()
    assert request is not None
    assert request[:3] == (200, 1, 99)
    assert Path(request[3]).exists()
    connection.close()
