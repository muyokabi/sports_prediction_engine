from collections.abc import Iterable, Iterator


def fixture_batches(fixture_ids: Iterable[int], size: int = 20) -> Iterator[list[int]]:
    if not 1 <= size <= 20:
        raise ValueError("API-Football fixture batches must contain 1 to 20 IDs")
    batch: list[int] = []
    for fixture_id in fixture_ids:
        batch.append(fixture_id)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
