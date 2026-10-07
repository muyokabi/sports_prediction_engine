import json
import pickle
from pathlib import Path
from typing import Any


def save_pickle(value: Any, path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Model artifact already exists: {path}")
    path.write_bytes(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
    path.with_suffix(path.suffix + ".json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )


def load_pickle(path: Path) -> Any:
    return pickle.loads(path.read_bytes())


def write_artifact_metadata(path: Path, metadata: dict[str, Any]) -> None:
    """Write the complete immutable training manifest beside a model artifact."""
    metadata_path = path.with_suffix(path.suffix + ".json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str), encoding="utf-8")
