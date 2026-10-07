from typing import Any

from sports_engine.sports.football.domain.team import TeamRecord, VenueRecord


def normalize_team(payload: dict[str, Any]) -> TeamRecord:
    team = payload["team"]
    venue = payload.get("venue")
    return TeamRecord(
        provider_team_id=team["id"],
        name=team["name"],
        code=team.get("code"),
        country=team.get("country"),
        founded=team.get("founded"),
        national=team.get("national"),
        logo_url=team.get("logo"),
        venue=VenueRecord(
            provider_venue_id=venue.get("id"),
            name=venue.get("name"),
            address=venue.get("address"),
            city=venue.get("city"),
            capacity=venue.get("capacity"),
            surface=venue.get("surface"),
        )
        if venue
        else None,
    )
