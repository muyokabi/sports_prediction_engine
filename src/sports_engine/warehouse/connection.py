from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb


def connect(path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


@contextmanager
def database(path: Path, *, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = connect(path, read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()
