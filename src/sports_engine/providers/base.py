from collections.abc import Mapping
from typing import Any, Protocol

from sports_engine.core.enums import Priority


class SportsDataProvider(Protocol):
    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]: ...
