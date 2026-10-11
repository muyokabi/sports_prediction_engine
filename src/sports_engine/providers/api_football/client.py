import json
import logging
import time
import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import duckdb
import httpx
from pydantic import ValidationError

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import ProviderError, ProviderRateLimitError, ProviderUnavailableError
from sports_engine.core.ids import query_hash
from sports_engine.core.retry import backoff_seconds
from sports_engine.providers.api_football.auth import ApiFootballCredentials
from sports_engine.providers.api_football.errors import (
    ApiFootballAuthenticationError,
    ApiFootballInvalidParametersError,
    ApiFootballMalformedResponseError,
    ApiFootballPlanRestrictionError,
)
from sports_engine.providers.api_football.quota import QuotaObservation
from sports_engine.providers.api_football.rate_limiter import SlidingWindowRateLimiter
from sports_engine.providers.api_football.schemas import ApiEnvelope, ApiStatusEnvelope
from sports_engine.providers.capabilities import ProviderCapabilities
from sports_engine.quota.budget import QuotaBudget
from sports_engine.warehouse.raw_store import RawArtifact, RawStore

LOG = logging.getLogger(__name__)
SAFE_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class ApiFootballClient:
    """Typed, quota-aware API-Football v3 client with raw-first persistence."""

    def __init__(
        self,
        credentials: ApiFootballCredentials,
        raw_store: RawStore,
        quota_budget: QuotaBudget,
        connection: duckdb.DuckDBPyConnection,
        *,
        timeout_seconds: float = 30.0,
        retry_count: int = 3,
        backoff_base_seconds: float = 0.5,
        minute_limit: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.raw_store = raw_store
        self.quota_budget = quota_budget
        self.connection = connection
        self.retry_count = retry_count
        self.backoff_base_seconds = backoff_base_seconds
        self.rate_limiter = SlidingWindowRateLimiter(minute_limit)
        self.subscription_plan: str | None = None
        self.capabilities: ProviderCapabilities | None = None
        self._client = httpx.Client(
            base_url=credentials.base_url,
            headers=credentials.headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiFootballClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_envelope(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> ApiEnvelope:
        request_id = uuid.uuid4()
        started_at = datetime.now(UTC)
        parameter_dict = dict(parameters)
        response: httpx.Response | None = None
        envelope: ApiEnvelope | None = None
        artifact: RawArtifact | None = None
        last_error: Exception | None = None
        self.quota_budget.authorize(priority)
        for attempt in range(self.retry_count + 1):
            self.rate_limiter.acquire()
            try:
                response = self._client.get(endpoint, params=parameter_dict)
                observed_at = datetime.now(UTC)
                quota = QuotaObservation.from_headers(response.headers, observed_at)
                self._refresh_from_headers(quota, observed_at)
                if response.status_code in {401, 403}:
                    raise ApiFootballAuthenticationError(
                        f"API-Football authentication failed with HTTP {response.status_code}"
                    )
                if response.status_code in SAFE_RETRY_STATUSES:
                    if response.status_code == 429 and attempt == self.retry_count:
                        raise ProviderRateLimitError("API-Football rate limit exceeded")
                    response.raise_for_status()
                response.raise_for_status()
                payload = response.json()
                envelope = ApiEnvelope.model_validate(payload)
                artifact = self.raw_store.write(
                    endpoint=endpoint,
                    purpose=purpose,
                    retrieved_at=observed_at,
                    parameters=parameter_dict,
                    job_run_id=job_run_id,
                    http_status=response.status_code,
                    quota={
                        "daily_limit": quota.daily_limit,
                        "daily_remaining": quota.daily_remaining,
                        "minute_limit": quota.minute_limit,
                        "minute_remaining": quota.minute_remaining,
                    },
                    payload=payload,
                )
                if envelope.has_errors:
                    raise self._api_error(endpoint, parameter_dict, envelope.errors, job_run_id)
                last_error = None
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = response is None or response.status_code in SAFE_RETRY_STATUSES
                if not retryable or attempt >= self.retry_count:
                    break
                retry_after = response.headers.get("retry-after") if response is not None else None
                try:
                    retry_after_seconds = float(retry_after) if retry_after is not None else 0.0
                except ValueError:
                    retry_after_seconds = 0.0
                time.sleep(max(retry_after_seconds, backoff_seconds(attempt, self.backoff_base_seconds)))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = ApiFootballMalformedResponseError(f"Malformed API-Football response: {exc}")
                break
            except ProviderError as exc:
                last_error = exc
                break
        completed_at = datetime.now(UTC)
        self._record_request(
            request_id=request_id,
            endpoint=endpoint,
            parameters=parameter_dict,
            started_at=started_at,
            completed_at=completed_at,
            response=response,
            envelope=envelope,
            purpose=purpose,
            priority=priority,
            job_run_id=job_run_id,
            artifact=artifact,
        )
        if last_error is not None or envelope is None or artifact is None:
            if isinstance(last_error, ProviderError):
                raise last_error
            raise ProviderUnavailableError(f"API-Football request failed: {last_error}") from last_error
        LOG.info(
            "provider_request endpoint=%s status=%s elapsed_ms=%.1f results=%s quota_remaining=%s",
            endpoint,
            response.status_code if response is not None else None,
            (completed_at - started_at).total_seconds() * 1000,
            envelope.results,
            self.quota_budget.observation.daily_remaining if self.quota_budget.observation else None,
        )
        return envelope

    def get_status(self, *, purpose: str = "provider_status", job_run_id: str | None = None) -> ProviderCapabilities:
        """Fetch API-Football account status; the provider documents this endpoint as quota-free."""
        request_id = uuid.uuid4()
        started_at = datetime.now(UTC)
        response: httpx.Response | None = None
        artifact: RawArtifact | None = None
        status: ApiStatusEnvelope | None = None
        error: Exception | None = None
        try:
            self.rate_limiter.acquire()
            response = self._client.get("/status")
            observed_at = datetime.now(UTC)
            header_quota = QuotaObservation.from_headers(response.headers, observed_at)
            if response.status_code in {401, 403}:
                raise ApiFootballAuthenticationError(
                    f"API-Football authentication failed with HTTP {response.status_code}"
                )
            if response.status_code == 429:
                raise ProviderRateLimitError("API-Football rate limit exceeded")
            response.raise_for_status()
            payload = response.json()
            status = ApiStatusEnvelope.model_validate(payload)
            artifact = self.raw_store.write(
                endpoint="/status",
                purpose=purpose,
                retrieved_at=observed_at,
                parameters={},
                job_run_id=job_run_id,
                http_status=response.status_code,
                quota={
                    "daily_limit": header_quota.daily_limit,
                    "daily_remaining": header_quota.daily_remaining,
                    "minute_limit": header_quota.minute_limit,
                    "minute_remaining": header_quota.minute_remaining,
                },
                payload=payload,
            )
            if status.has_errors:
                raise self._api_error("/status", {}, status.errors, job_run_id)
            self.subscription_plan = str(status.response.subscription.get("plan") or "") or None
            self.capabilities = self._capabilities_from_status(status, header_quota, observed_at)
            self.quota_budget.update(
                QuotaObservation(
                    self.capabilities.daily_limit,
                    self.capabilities.daily_remaining,
                    self.capabilities.minute_limit,
                    self.capabilities.minute_remaining,
                    observed_at,
                )
            )
            self.rate_limiter.update_maximum(self.capabilities.minute_limit)
            self._persist_capabilities(self.capabilities, artifact)
        except (json.JSONDecodeError, ValidationError) as exc:
            error = ApiFootballMalformedResponseError(f"Malformed API-Football status response: {exc}")
        except (httpx.HTTPError, ProviderError) as exc:
            error = exc
        completed_at = datetime.now(UTC)
        self._record_status_request(
            request_id, started_at, completed_at, response, status, purpose, job_run_id, artifact
        )
        if error is not None:
            if isinstance(error, ProviderError):
                raise error
            raise ProviderUnavailableError(f"API-Football status request failed: {error}") from error
        if status is None:
            raise ApiFootballMalformedResponseError("API-Football status response was empty")
        if self.capabilities is None:
            raise ApiFootballMalformedResponseError("API-Football capabilities could not be derived")
        return self.capabilities

    def _capabilities_from_status(
        self,
        status: ApiStatusEnvelope,
        headers: QuotaObservation,
        observed_at: datetime,
    ) -> ProviderCapabilities:
        subscription = status.response.subscription
        requests = status.response.requests
        body_limit = self._optional_int(requests.get("limit_day"))
        body_used = self._optional_int(requests.get("current"))
        body_remaining = body_limit - body_used if body_limit is not None and body_used is not None else None
        if headers.daily_limit is not None and body_limit is not None and headers.daily_limit != body_limit:
            LOG.warning(
                "provider_quota_discrepancy field=daily_limit status=%s header=%s",
                body_limit,
                headers.daily_limit,
            )
        if (
            headers.daily_remaining is not None
            and body_remaining is not None
            and headers.daily_remaining != body_remaining
        ):
            LOG.warning(
                "provider_quota_discrepancy field=daily_remaining status=%s header=%s",
                body_remaining,
                headers.daily_remaining,
            )
        daily_limit = headers.daily_limit if headers.daily_limit is not None else body_limit
        daily_remaining = headers.daily_remaining if headers.daily_remaining is not None else body_remaining
        used = daily_limit - daily_remaining if daily_limit is not None and daily_remaining is not None else body_used
        return ProviderCapabilities(
            provider="api_football",
            subscription_plan=self.subscription_plan,
            subscription_active=subscription.get("active"),
            subscription_end=str(subscription["end"]) if subscription.get("end") is not None else None,
            requests_used_today=used,
            daily_limit=daily_limit,
            daily_remaining=daily_remaining,
            minute_limit=headers.minute_limit,
            minute_remaining=headers.minute_remaining,
            observed_at=observed_at,
        )

    def _refresh_from_headers(self, quota: QuotaObservation, observed_at: datetime) -> None:
        if not any(
            value is not None
            for value in (
                quota.daily_limit,
                quota.daily_remaining,
                quota.minute_limit,
                quota.minute_remaining,
            )
        ):
            return
        previous = self.capabilities
        daily_limit = (
            quota.daily_limit if quota.daily_limit is not None else (previous.daily_limit if previous else None)
        )
        daily_remaining = (
            quota.daily_remaining
            if quota.daily_remaining is not None
            else (previous.daily_remaining if previous else None)
        )
        self.capabilities = ProviderCapabilities(
            provider="api_football",
            subscription_plan=previous.subscription_plan if previous else self.subscription_plan,
            subscription_active=previous.subscription_active if previous else None,
            subscription_end=previous.subscription_end if previous else None,
            requests_used_today=(
                daily_limit - daily_remaining if daily_limit is not None and daily_remaining is not None else None
            ),
            daily_limit=daily_limit,
            daily_remaining=daily_remaining,
            minute_limit=(
                quota.minute_limit if quota.minute_limit is not None else (previous.minute_limit if previous else None)
            ),
            minute_remaining=(
                quota.minute_remaining
                if quota.minute_remaining is not None
                else (previous.minute_remaining if previous else None)
            ),
            observed_at=observed_at,
        )
        self.quota_budget.update(
            QuotaObservation(
                self.capabilities.daily_limit,
                self.capabilities.daily_remaining,
                self.capabilities.minute_limit,
                self.capabilities.minute_remaining,
                observed_at,
            )
        )
        self.rate_limiter.update_maximum(self.capabilities.minute_limit)
        self._persist_capabilities(self.capabilities, None)

    def _persist_capabilities(self, capabilities: ProviderCapabilities, artifact: RawArtifact | None) -> None:
        self.connection.execute(
            "INSERT INTO provider_capabilities "
            "(capability_id, provider, observed_at, subscription_plan, subscription_active, "
            "requests_current, requests_limit_daily, production_season, production_accessible, "
            "replay_season, replay_accessible, raw_path, subscription_end, daily_remaining, "
            "minute_limit, minute_remaining) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?)",
            [
                uuid.uuid4(),
                capabilities.provider,
                capabilities.observed_at,
                capabilities.subscription_plan,
                capabilities.subscription_active,
                capabilities.requests_used_today,
                capabilities.daily_limit,
                str(artifact.payload_path) if artifact else None,
                capabilities.subscription_end,
                capabilities.daily_remaining,
                capabilities.minute_limit,
                capabilities.minute_remaining,
            ],
        )

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _api_error(
        self,
        endpoint: str,
        parameters: dict[str, Any],
        errors: list[Any] | dict[str, Any],
        job_run_id: str | None,
    ) -> ProviderError:
        message = json.dumps(errors, sort_keys=True)
        if isinstance(errors, dict):
            lowered = {str(key).lower(): str(value) for key, value in errors.items()}
            if "plan" in lowered:
                return ApiFootballPlanRestrictionError(
                    endpoint=endpoint,
                    parameters=parameters,
                    provider_message=lowered["plan"],
                    subscription_plan=self.subscription_plan,
                    job_run_id=job_run_id,
                )
            if any(key in lowered for key in ("token", "auth", "account", "key")):
                return ApiFootballAuthenticationError(f"API-Football authentication error: {message}")
            if any(key in lowered for key in ("requests", "rate", "limit")):
                return ProviderRateLimitError(f"API-Football rate limit error: {message}")
            if any(key in lowered for key in ("parameters", "parameter", "league", "season", "fixture")):
                return ApiFootballInvalidParametersError(f"API-Football parameter error: {message}")
        return ProviderError(f"API-Football errors: {message}")

    def _record_status_request(
        self,
        request_id: uuid.UUID,
        started_at: datetime,
        completed_at: datetime,
        response: httpx.Response | None,
        status: ApiStatusEnvelope | None,
        purpose: str,
        job_run_id: str | None,
        artifact: RawArtifact | None,
    ) -> None:
        capabilities = self.capabilities
        limit = capabilities.daily_limit if capabilities else None
        remaining = capabilities.daily_remaining if capabilities else None
        self.connection.execute(
            "INSERT INTO api_request_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                request_id,
                "api_football",
                "/status",
                query_hash({}),
                started_at,
                completed_at,
                response.status_code if response is not None else None,
                json.dumps(status.errors if status else []),
                status.results if status else None,
                None,
                None,
                limit,
                remaining,
                capabilities.minute_limit if capabilities else None,
                capabilities.minute_remaining if capabilities else None,
                purpose,
                Priority.P0.value,
                job_run_id,
                (completed_at - started_at).total_seconds() * 1000,
                str(artifact.payload_path) if artifact else None,
            ],
        )

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_envelope(
            endpoint, parameters, purpose=purpose, priority=priority, job_run_id=job_run_id
        ).response

    def get_all_pages(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        page = int(parameters.get("page", 1))
        while True:
            envelope = self.get_envelope(
                endpoint,
                {**parameters, "page": page},
                purpose=purpose,
                priority=priority,
                job_run_id=job_run_id,
            )
            yield from envelope.response
            if envelope.paging.current >= envelope.paging.total:
                return
            page = envelope.paging.current + 1

    def _record_request(
        self,
        *,
        request_id: uuid.UUID,
        endpoint: str,
        parameters: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
        response: httpx.Response | None,
        envelope: ApiEnvelope | None,
        purpose: str,
        priority: Priority,
        job_run_id: str | None,
        artifact: RawArtifact | None,
    ) -> None:
        quota = self.quota_budget.observation
        self.connection.execute(
            "INSERT INTO api_request_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                request_id,
                "api_football",
                endpoint,
                query_hash(parameters),
                started_at,
                completed_at,
                response.status_code if response is not None else None,
                json.dumps(envelope.errors if envelope else []),
                envelope.results if envelope else None,
                envelope.paging.current if envelope else None,
                envelope.paging.total if envelope else None,
                quota.daily_limit if quota else None,
                quota.daily_remaining if quota else None,
                quota.minute_limit if quota else None,
                quota.minute_remaining if quota else None,
                purpose,
                priority.value,
                job_run_id,
                (completed_at - started_at).total_seconds() * 1000,
                str(artifact.payload_path) if artifact else None,
            ],
        )
