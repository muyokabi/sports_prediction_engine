from pathlib import Path

import polars as pl


def write_immutable(frame: pl.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Immutable Parquet artifact already exists: {path}")
    frame.write_parquet(path, compression="zstd", statistics=True)
    return path
