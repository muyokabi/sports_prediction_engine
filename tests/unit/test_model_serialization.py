import json
from pathlib import Path

import pytest

from sports_engine.models.serialization import load_pickle, save_pickle


def test_new_pickle_artifact_is_hash_verified(tmp_path: Path) -> None:
    path = tmp_path / "model.pkl"
    save_pickle({"model": "trusted"}, path, {"kind": "test"})
    assert load_pickle(path) == {"model": "trusted"}

    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="integrity check failed"):
        load_pickle(path)


def test_legacy_pickle_without_digest_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "model.pkl"
    save_pickle({"model": "legacy"}, path, {})
    metadata_path = path.with_suffix(".pkl.json")
    metadata_path.write_text(json.dumps({"kind": "legacy"}), encoding="utf-8")
    assert load_pickle(path) == {"model": "legacy"}
