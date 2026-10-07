from dataclasses import dataclass
from typing import Any

from sports_engine.providers.api_football.schemas import Coverage


@dataclass(frozen=True, slots=True)
class CoverageDecision:
    accepted: bool
    reasons: tuple[str, ...]
    profile: Coverage


def assess_coverage(payload: dict[str, Any]) -> CoverageDecision:
    profile = Coverage.model_validate(payload)
    requirements = {
        "fixtures.events": profile.fixtures.events,
        "fixtures.lineups": profile.fixtures.lineups,
        "fixtures.statistics_fixtures": profile.fixtures.statistics_fixtures,
        "fixtures.statistics_players": profile.fixtures.statistics_players,
        "odds": profile.odds,
    }
    reasons = tuple(f"{name}=false" for name, available in requirements.items() if not available)
    return CoverageDecision(not reasons, reasons, profile)
