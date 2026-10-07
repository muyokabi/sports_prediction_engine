from collections.abc import Iterator
from contextlib import contextmanager

import duckdb


@contextmanager
def transaction(connection: duckdb.DuckDBPyConnection) -> Iterator[duckdb.DuckDBPyConnection]:
    connection.begin()
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
