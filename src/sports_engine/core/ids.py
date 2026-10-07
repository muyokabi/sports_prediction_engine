import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

NAMESPACE = uuid.UUID("3b79cba0-0af7-44f1-a840-f00d282bdbbe")


def canonical_id(entity_type: str, provider: str, provider_id: str | int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{entity_type}:{provider}:{provider_id}")


def query_hash(parameters: Mapping[str, Any]) -> str:
    payload = json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
