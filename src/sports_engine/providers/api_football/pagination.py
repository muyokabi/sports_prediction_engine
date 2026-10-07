from collections.abc import Callable, Iterator
from typing import Any

from sports_engine.providers.api_football.schemas import ApiEnvelope


def pages(fetch: Callable[[dict[str, Any]], ApiEnvelope], parameters: dict[str, Any]) -> Iterator[ApiEnvelope]:
    requested_page = int(parameters.get("page", 1))
    while True:
        envelope = fetch({**parameters, "page": requested_page})
        yield envelope
        if envelope.paging.current >= envelope.paging.total:
            return
        requested_page = envelope.paging.current + 1
