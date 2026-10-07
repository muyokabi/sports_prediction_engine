from pydantic import BaseModel


class VenueRecord(BaseModel):
    provider_venue_id: int | None
    name: str | None = None
    address: str | None = None
    city: str | None = None
    capacity: int | None = None
    surface: str | None = None


class TeamRecord(BaseModel):
    provider_team_id: int
    name: str
    code: str | None = None
    country: str | None = None
    founded: int | None = None
    national: bool | None = None
    logo_url: str | None = None
    venue: VenueRecord | None = None
