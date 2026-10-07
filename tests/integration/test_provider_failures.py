from pathlib import Path

import duckdb
import httpx
import pytest

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import ProviderError, ProviderRateLimitError
from sports_engine.providers.api_football.auth import ApiFootballCredentials
from sports_engine.providers.api_football.client import ApiFootballClient
from sports_engine.providers.api_football.errors import (
    ApiFootballInvalidParametersError,
    ApiFootballPlanRestrictionError,
)
from sports_engine.quota.budget import QuotaBudget, QuotaPolicy
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.raw_store import RawStore


def make_client(
    tmp_path: Path, transport: httpx.MockTransport, retries: int = 1
) -> tuple[ApiFootballClient, duckdb.DuckDBPyConnection]:
    connection = connect(tmp_path / "provider.duckdb")
    migrate(connection)
    client = ApiFootballClient(
        ApiFootballCredentials("secret", "https://example.test"),
        RawStore(tmp_path / "raw"),
        QuotaBudget(QuotaPolicy(10, 2)),
        connection,
        retry_count=retries,
        backoff_base_seconds=0,
        transport=transport,
    )
    return client, connection


def envelope(*, errors: object = None) -> dict[str, object]:
    return {
        "get": "fixtures",
        "parameters": {},
        "errors": [] if errors is None else errors,
        "results": 0,
        "paging": {"current": 1, "total": 1},
        "response": [],
    }


def test_safe_server_error_is_retried(tmp_path: Path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json=envelope())

    client, connection = make_client(tmp_path, httpx.MockTransport(handler))
    assert client.get("/fixtures", {}, purpose="retry", priority=Priority.P1) == []
    assert calls == 2
    assert connection.execute("SELECT http_status FROM api_request_log").fetchone() == (200,)
    client.close()
    connection.close()


def test_api_level_errors_are_logged_and_raised(tmp_path: Path) -> None:
    client, connection = make_client(
        tmp_path,
        httpx.MockTransport(lambda _: httpx.Response(200, json=envelope(errors={"league": "invalid"}))),
        retries=0,
    )
    with pytest.raises(ProviderError, match="league"):
        client.get("/fixtures", {}, purpose="api_error", priority=Priority.P1)
    row = connection.execute("SELECT http_status, api_errors FROM api_request_log").fetchone()
    assert row is not None and row[0] == 200 and "league" in row[1]
    raw_path = connection.execute("SELECT raw_path FROM api_request_log").fetchone()
    assert raw_path is not None and raw_path[0] is not None and Path(raw_path[0]).exists()
    client.close()
    connection.close()


def test_terminal_rate_limit_keeps_specific_error_and_status(tmp_path: Path) -> None:
    client, connection = make_client(
        tmp_path,
        httpx.MockTransport(lambda _: httpx.Response(429, headers={"retry-after": "0"})),
        retries=0,
    )
    with pytest.raises(ProviderRateLimitError):
        client.get("/fixtures", {}, purpose="rate_limit", priority=Priority.P1)
    assert connection.execute("SELECT http_status FROM api_request_log").fetchone() == (429,)
    client.close()
    connection.close()


def test_plan_restriction_preserves_request_context(tmp_path: Path) -> None:
    client, connection = make_client(
        tmp_path,
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json=envelope(errors={"plan": "Free plans only support seasons through 2024"}),
            )
        ),
        retries=0,
    )
    with pytest.raises(ApiFootballPlanRestrictionError) as raised:
        client.get(
            "/teams",
            {"league": 39, "season": 2026},
            purpose="plan",
            priority=Priority.P1,
            job_run_id=None,
        )
    assert raised.value.endpoint == "/teams"
    assert raised.value.parameters == {"league": 39, "season": 2026}
    assert raised.value.requested_season == 2026
    assert raised.value.provider_message == "Free plans only support seasons through 2024"
    client.close()
    connection.close()


def test_parameter_error_has_specific_type(tmp_path: Path) -> None:
    client, connection = make_client(
        tmp_path,
        httpx.MockTransport(lambda _: httpx.Response(200, json=envelope(errors={"league": "invalid"}))),
        retries=0,
    )
    with pytest.raises(ApiFootballInvalidParametersError):
        client.get("/fixtures", {}, purpose="parameters", priority=Priority.P1)
    client.close()
    connection.close()


def test_status_wrapper_is_validated_and_plan_is_retained(tmp_path: Path) -> None:
    payload = {
        "get": "status",
        "parameters": [],
        "errors": [],
        "results": 1,
        "response": {
            "account": {"firstname": "Test"},
            "subscription": {"plan": "Free", "active": True},
            "requests": {"current": 12, "limit_day": 100},
        },
    }
    client, connection = make_client(
        tmp_path, httpx.MockTransport(lambda _: httpx.Response(200, json=payload)), retries=0
    )
    status = client.get_status()
    assert status.subscription_plan == "Free"
    assert status.daily_limit == 100
    assert status.daily_remaining == 88
    assert client.subscription_plan == "Free"
    assert connection.execute("SELECT endpoint, requests_remaining_daily FROM api_request_log").fetchone() == (
        "/status",
        88,
    )
    client.close()
    connection.close()


def test_quota_transitions_follow_reported_status_and_headers(tmp_path: Path) -> None:
    observations = [
        ("Free", 100, 7, 10, 8),
        ("Pro", 7_500, 31, 300, 298),
        ("Free", 100, 5, 10, 9),
    ]
    call = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call
        plan, daily_limit, used, minute_limit, minute_remaining = observations[call]
        call += 1
        return httpx.Response(
            200,
            headers={
                "x-ratelimit-requests-limit": str(daily_limit),
                "x-ratelimit-requests-remaining": str(daily_limit - used),
                "X-RateLimit-Limit": str(minute_limit),
                "X-RateLimit-Remaining": str(minute_remaining),
            },
            json={
                "get": "status",
                "parameters": [],
                "errors": [],
                "results": 1,
                "response": {
                    "account": {},
                    "subscription": {"plan": plan, "active": True},
                    "requests": {"current": used, "limit_day": daily_limit},
                },
            },
        )

    client, connection = make_client(tmp_path, httpx.MockTransport(handler), retries=0)
    free = client.get_status()
    pro = client.get_status()
    downgraded = client.get_status()
    assert (free.daily_limit, free.minute_limit) == (100, 10)
    assert (pro.daily_limit, pro.daily_remaining, pro.minute_limit) == (7_500, 7_469, 300)
    assert (downgraded.daily_limit, downgraded.minute_limit) == (100, 10)
    assert client.quota_budget.observation is not None
    assert client.quota_budget.observation.daily_limit == 100
    assert client.rate_limiter.maximum == 10
    client.close()
    connection.close()


def test_fresh_headers_override_stale_status_and_log_discrepancy(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    payload = {
        "get": "status",
        "parameters": [],
        "errors": [],
        "results": 1,
        "response": {
            "account": {},
            "subscription": {"plan": "Pro", "active": True},
            "requests": {"current": 99, "limit_day": 100},
        },
    }
    headers = {
        "x-ratelimit-requests-limit": "7500",
        "x-ratelimit-requests-remaining": "7469",
        "X-RateLimit-Limit": "300",
        "X-RateLimit-Remaining": "298",
    }
    client, connection = make_client(
        tmp_path,
        httpx.MockTransport(lambda _: httpx.Response(200, headers=headers, json=payload)),
        retries=0,
    )
    with caplog.at_level("WARNING"):
        status = client.get_status()
    assert (status.daily_limit, status.daily_remaining) == (7_500, 7_469)
    assert "provider_quota_discrepancy" in caplog.text
    client.close()
    connection.close()
