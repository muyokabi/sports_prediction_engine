from datetime import UTC, datetime, timedelta

import pytest

from sports_engine.markets.reference import (
    ReferenceQuote,
    ReferenceState,
    classify_reference,
    summarize_references,
)


def quote(
    bookmaker_id: str,
    odds: float,
    observed_at: datetime,
    *,
    snapshot: str,
    fair_probability: float = 0.5,
) -> ReferenceQuote:
    return ReferenceQuote(
        snapshot,
        bookmaker_id,
        f"Book {bookmaker_id}",
        "market",
        "selection",
        odds,
        fair_probability,
        observed_at,
        None,
        "raw.json",
    )


def test_aged_reference_is_informational_not_invalid() -> None:
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    aged = quote("a", 2.1, now - timedelta(hours=8), snapshot="old")
    assert (
        classify_reference(
            aged,
            analysis_timestamp=now,
            kickoff_timestamp=now + timedelta(days=1),
            aged_reference_minutes=180,
        )
        == ReferenceState.AGED_REFERENCE
    )
    summary = summarize_references(
        [aged],
        analysis_timestamp=now,
        kickoff_timestamp=now + timedelta(days=1),
        aged_reference_minutes=180,
    )
    assert summary.best == aged


def test_latest_per_bookmaker_prevents_old_high_price_substitution() -> None:
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    values = [
        quote("a", 2.4, now - timedelta(hours=8), snapshot="a-old"),
        quote("a", 1.9, now - timedelta(hours=2), snapshot="a-new"),
        quote("b", 2.0, now - timedelta(hours=3), snapshot="b-new"),
    ]
    summary = summarize_references(
        values,
        analysis_timestamp=now,
        kickoff_timestamp=now + timedelta(days=1),
        aged_reference_minutes=180,
    )
    assert {item.snapshot_id for item in summary.latest_per_bookmaker} == {"a-new", "b-new"}
    assert summary.best is not None and summary.best.snapshot_id == "b-new"
    assert summary.worst is not None and summary.worst.decimal_odds == pytest.approx(1.9)
    assert summary.snapshot_count == 3


def test_post_kickoff_and_malformed_references_are_invalid() -> None:
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    kickoff = now - timedelta(hours=1)
    post = quote("a", 2.0, now - timedelta(minutes=30), snapshot="post")
    malformed = quote("b", 1.0, now - timedelta(hours=2), snapshot="bad")
    assert (
        classify_reference(post, analysis_timestamp=now, kickoff_timestamp=kickoff, aged_reference_minutes=180)
        == ReferenceState.POST_KICKOFF_INVALID
    )
    assert (
        classify_reference(
            malformed,
            analysis_timestamp=now,
            kickoff_timestamp=now + timedelta(hours=1),
            aged_reference_minutes=180,
        )
        == ReferenceState.INVALID_REFERENCE
    )


def test_multiple_bookmaker_consensus_dispersion_and_movement_use_latest_quotes() -> None:
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    values = [
        quote("a", 2.20, now - timedelta(hours=5), snapshot="a-first", fair_probability=0.44),
        quote("a", 2.10, now - timedelta(hours=1), snapshot="a-latest", fair_probability=0.48),
        quote("b", 2.00, now - timedelta(hours=2), snapshot="b-latest", fair_probability=0.46),
    ]
    summary = summarize_references(
        values,
        analysis_timestamp=now,
        kickoff_timestamp=now + timedelta(days=1),
        aged_reference_minutes=180,
    )
    assert summary.consensus_probability == pytest.approx(0.47)
    assert summary.bookmaker_dispersion == pytest.approx(0.10)
    assert summary.best is not None and summary.best.snapshot_id == "a-latest"
    assert summary.price_movement == pytest.approx(-0.10)
