import gzip
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RawArtifact:
    payload_path: Path
    metadata_path: Path
    content_hash: str


class RawStore:
    """Write-once gzip JSON payload storage with auditable sidecars."""

    def __init__(self, root: Path, provider: str = "api_football") -> None:
        self.root = root / provider

    def write(
        self,
        *,
        endpoint: str,
        purpose: str,
        retrieved_at: datetime,
        parameters: dict[str, Any],
        job_run_id: str | None,
        http_status: int,
        quota: dict[str, int | None],
        payload: dict[str, Any],
    ) -> RawArtifact:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        content_hash = hashlib.sha256(encoded).hexdigest()
        directory = self.root / retrieved_at.strftime("%Y/%m/%d")
        directory.mkdir(parents=True, exist_ok=True)
        safe_endpoint = _safe_component(endpoint.strip("/").replace("/", "_")) or "root"
        safe_purpose = _safe_component(purpose) or "unspecified"
        timestamp = retrieved_at.strftime("%Y%m%dT%H%M%S%fZ")
        stem = f"{safe_endpoint}_{safe_purpose}_{timestamp}_{content_hash[:12]}"
        payload_path = directory / f"{stem}.json.gz"
        metadata_path = directory / f"{stem}.metadata.json"
        if payload_path.exists() or metadata_path.exists():
            raise FileExistsError(f"Raw artifact collision: {stem}")
        with (
            payload_path.open("xb") as raw_file,
            gzip.GzipFile(fileobj=raw_file, mode="wb", mtime=0) as compressed,
        ):
            compressed.write(encoded)
        metadata = {
            "retrieved_at_utc": retrieved_at.isoformat(),
            "endpoint": endpoint,
            "parameters": parameters,
            "job_run_id": job_run_id,
            "http_status": http_status,
            "quota": quota,
            "content_hash": content_hash,
        }
        fd = os.open(metadata_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, "w", encoding="utf-8") as sidecar:
            json.dump(metadata, sidecar, indent=2, sort_keys=True)
        return RawArtifact(payload_path, metadata_path, content_hash)


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
