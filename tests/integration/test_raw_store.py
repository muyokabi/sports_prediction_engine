import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from sports_engine.warehouse.raw_store import RawStore


def test_raw_store_writes_gzip_and_sidecar(tmp_path: Path) -> None:
    artifact = RawStore(tmp_path).write(
        endpoint="/fixtures",
        purpose="contract",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        parameters={"id": 1},
        job_run_id="run",
        http_status=200,
        quota={"daily_remaining": 99},
        payload={"response": []},
    )
    with gzip.open(artifact.payload_path, "rt", encoding="utf-8") as handle:
        assert json.load(handle) == {"response": []}
    metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
    assert metadata["content_hash"] == artifact.content_hash


def test_raw_store_sanitizes_windows_reserved_filename_characters(tmp_path: Path) -> None:
    artifact = RawStore(tmp_path).write(
        endpoint="/players/squads",
        purpose="squad_reference:39:2026",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        parameters={"team": 39},
        job_run_id=None,
        http_status=200,
        quota={},
        payload={"response": []},
    )
    assert ":" not in artifact.payload_path.name
    metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
    assert metadata["endpoint"] == "/players/squads"
    assert metadata["parameters"] == {"team": 39}
