from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

FINAL_STATUSES = frozenset({"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"})


class DependencyState(StrEnum):
    CLEAR = "CLEAR"
    BLOCKED_BY_INTERVENING_FIXTURE = "BLOCKED_BY_INTERVENING_FIXTURE"
    DEPENDENCY_RESOLVED = "DEPENDENCY_RESOLVED"


class FreshnessState(StrEnum):
    CURRENT = "CURRENT"
    MODEL_STATE_STALE = "MODEL_STATE_STALE"
    MARKET_PRICE_STALE = "MARKET_PRICE_STALE"
    STALE_INTERVENING_FIXTURE = "STALE_INTERVENING_FIXTURE"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class ScheduledFixture:
    fixture_id: str
    kickoff: datetime
    home_team_id: str
    away_team_id: str
    status: str
    enriched: bool = False
    quality_passed: bool = False


@dataclass(frozen=True, slots=True)
class DependencyAssessment:
    intervening_fixture_ids: tuple[str, ...]
    unresolved_fixture_ids: tuple[str, ...]
    state: DependencyState


def assess_intervening_fixtures(
    target: ScheduledFixture,
    schedule: list[ScheduledFixture],
    *,
    analysis_timestamp: datetime,
) -> DependencyAssessment:
    team_ids = {target.home_team_id, target.away_team_id}
    intervening = sorted(
        (
            fixture
            for fixture in schedule
            if fixture.fixture_id != target.fixture_id
            and analysis_timestamp < fixture.kickoff < target.kickoff
            and bool(team_ids & {fixture.home_team_id, fixture.away_team_id})
        ),
        key=lambda fixture: (fixture.kickoff, fixture.fixture_id),
    )
    unresolved = tuple(
        fixture.fixture_id
        for fixture in intervening
        if fixture.status not in FINAL_STATUSES or not fixture.enriched or not fixture.quality_passed
    )
    if unresolved:
        state = DependencyState.BLOCKED_BY_INTERVENING_FIXTURE
    elif intervening:
        state = DependencyState.DEPENDENCY_RESOLVED
    else:
        state = DependencyState.CLEAR
    return DependencyAssessment(tuple(fixture.fixture_id for fixture in intervening), unresolved, state)


def freshness_after_change(*, change: str, affects_team_state: bool) -> FreshnessState:
    if change == "new_odds" and not affects_team_state:
        return FreshnessState.MARKET_PRICE_STALE
    if change == "intervening_fixture":
        return FreshnessState.STALE_INTERVENING_FIXTURE
    return FreshnessState.MODEL_STATE_STALE
