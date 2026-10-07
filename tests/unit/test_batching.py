import pytest

from sports_engine.sports.football.ingestion.match_enrichment import fixture_batches


def test_fixture_batching_never_exceeds_twenty() -> None:
    assert [len(batch) for batch in fixture_batches(range(45))] == [20, 20, 5]


def test_fixture_batch_size_guard() -> None:
    with pytest.raises(ValueError):
        list(fixture_batches([1], 21))
