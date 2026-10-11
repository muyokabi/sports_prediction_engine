import json
import pickle
from hashlib import sha256
from pathlib import Path
from typing import Any


def save_pickle(value: Any, path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Model artifact already exists: {path}")
    payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    path.write_bytes(payload)
    path.with_suffix(path.suffix + ".json").write_text(
        json.dumps({**metadata, "artifact_sha256": sha256(payload).hexdigest()}, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def load_pickle(
    path: Path,
    *,
    metadata_path: Path | None = None,
    hash_field: str = "artifact_sha256",
) -> Any:
    """Load a trusted-local pickle after verifying its digest when one is recorded.

    Pickle remains unsafe for untrusted input. Digest verification detects corruption
    or replacement of new artifacts; manifests from older releases intentionally load
    without a digest so immutable local history remains usable.
    """
    payload = path.read_bytes()
    manifest_path = metadata_path or path.with_suffix(path.suffix + ".json")
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid artifact manifest: {manifest_path}") from exc
        expected = manifest.get(hash_field) if isinstance(manifest, dict) else None
        if expected is not None:
            actual = sha256(payload).hexdigest()
            if not isinstance(expected, str) or actual != expected:
                raise ValueError(f"Artifact integrity check failed: {path}")
    return pickle.loads(payload)


def write_artifact_metadata(path: Path, metadata: dict[str, Any]) -> None:
    """Write the complete immutable training manifest beside a model artifact."""
    metadata_path = path.with_suffix(path.suffix + ".json")
    payload = path.read_bytes()
    complete = {**metadata, "artifact_sha256": sha256(payload).hexdigest()}
    calibrator_path = path.parent / "calibrator.pkl"
    if calibrator_path.is_file():
        complete["calibrator_sha256"] = sha256(calibrator_path.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(complete, indent=2, sort_keys=True, default=str), encoding="utf-8")
