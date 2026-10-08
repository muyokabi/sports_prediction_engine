from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from statistics import median


class ReferenceState(StrEnum):
    CURRENT_REFERENCE = "CURRENT_REFERENCE"
    LATEST_PROVIDER_REFERENCE = "LATEST_PROVIDER_REFERENCE"
    AGED_REFERENCE = "AGED_REFERENCE"
    HISTORICAL_REFERENCE = "HISTORICAL_REFERENCE"
    NO_REFERENCE_ODDS = "NO_REFERENCE_ODDS"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    POST_KICKOFF_INVALID = "POST_KICKOFF_INVALID"


@dataclass(frozen=True, slots=True)
class ReferenceQuote:
    snapshot_id: str
    bookmaker_id: str
    bookmaker: str
    market_id: str
    selection_id: str
    decimal_odds: float
    fair_probability: float | None
    collected_at: datetime
    provider_updated_at: datetime | None
    source_raw_path: str
    is_current_run: bool = False

    @property
    def effective_timestamp(self) -> datetime:
        return self.provider_updated_at or self.collected_at


@dataclass(frozen=True, slots=True)
class ReferenceSummary:
    state: ReferenceState
    latest_per_bookmaker: tuple[ReferenceQuote, ...]
    best: ReferenceQuote | None
    worst: ReferenceQuote | None
    consensus_probability: float | None
    bookmaker_dispersion: float | None
    snapshot_count: int
    first_observed_odds: float | None
    price_movement: float | None


def classify_reference(
    quote: ReferenceQuote,
    *,
    analysis_timestamp: datetime,
    kickoff_timestamp: datetime,
    aged_reference_minutes: int,
) -> ReferenceState:
    if (
        quote.decimal_odds <= 1
        or quote.collected_at > analysis_timestamp
        or quote.effective_timestamp > analysis_timestamp
    ):
        return ReferenceState.INVALID_REFERENCE
    if quote.effective_timestamp >= kickoff_timestamp:
        return ReferenceState.POST_KICKOFF_INVALID
    if quote.is_current_run:
        return ReferenceState.CURRENT_REFERENCE
    age_minutes = (analysis_timestamp - quote.effective_timestamp).total_seconds() / 60
    if age_minutes > aged_reference_minutes:
        return ReferenceState.AGED_REFERENCE
    return ReferenceState.LATEST_PROVIDER_REFERENCE


def summarize_references(
    quotes: list[ReferenceQuote],
    *,
    analysis_timestamp: datetime,
    kickoff_timestamp: datetime,
    aged_reference_minutes: int,
) -> ReferenceSummary:
    if not quotes:
        return ReferenceSummary(ReferenceState.NO_REFERENCE_ODDS, (), None, None, None, None, 0, None, None)
    valid = [
        quote
        for quote in quotes
        if classify_reference(
            quote,
            analysis_timestamp=analysis_timestamp,
            kickoff_timestamp=kickoff_timestamp,
            aged_reference_minutes=aged_reference_minutes,
        )
        not in {ReferenceState.INVALID_REFERENCE, ReferenceState.POST_KICKOFF_INVALID}
    ]
    if not valid:
        states = {
            classify_reference(
                quote,
                analysis_timestamp=analysis_timestamp,
                kickoff_timestamp=kickoff_timestamp,
                aged_reference_minutes=aged_reference_minutes,
            )
            for quote in quotes
        }
        state = (
            ReferenceState.POST_KICKOFF_INVALID
            if ReferenceState.POST_KICKOFF_INVALID in states
            else ReferenceState.INVALID_REFERENCE
        )
        return ReferenceSummary(state, (), None, None, None, None, len(quotes), None, None)
    by_bookmaker: dict[str, ReferenceQuote] = {}
    for quote in valid:
        current = by_bookmaker.get(quote.bookmaker_id)
        if current is None or (quote.effective_timestamp, quote.collected_at, quote.snapshot_id) > (
            current.effective_timestamp,
            current.collected_at,
            current.snapshot_id,
        ):
            by_bookmaker[quote.bookmaker_id] = quote
    latest = tuple(sorted(by_bookmaker.values(), key=lambda quote: (quote.bookmaker, quote.bookmaker_id)))
    best = max(latest, key=lambda quote: quote.decimal_odds)
    worst = min(latest, key=lambda quote: quote.decimal_odds)
    states = {
        classify_reference(
            quote,
            analysis_timestamp=analysis_timestamp,
            kickoff_timestamp=kickoff_timestamp,
            aged_reference_minutes=aged_reference_minutes,
        )
        for quote in latest
    }
    if ReferenceState.CURRENT_REFERENCE in states:
        state = ReferenceState.CURRENT_REFERENCE
    elif states == {ReferenceState.AGED_REFERENCE}:
        state = ReferenceState.AGED_REFERENCE
    else:
        state = ReferenceState.LATEST_PROVIDER_REFERENCE
    probabilities = [quote.fair_probability for quote in latest if quote.fair_probability is not None]
    first = min(valid, key=lambda quote: (quote.effective_timestamp, quote.collected_at, quote.snapshot_id))
    same_book_history = [quote for quote in valid if quote.bookmaker_id == best.bookmaker_id]
    first_best_book = min(
        same_book_history,
        key=lambda quote: (quote.effective_timestamp, quote.collected_at, quote.snapshot_id),
    )
    return ReferenceSummary(
        state,
        latest,
        best,
        worst,
        float(median(probabilities)) if probabilities else None,
        best.decimal_odds - worst.decimal_odds if len(latest) > 1 else 0.0,
        len(valid),
        first.decimal_odds,
        best.decimal_odds - first_best_book.decimal_odds,
    )
