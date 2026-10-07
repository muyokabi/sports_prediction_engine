from pydantic import BaseModel


class SquadPlayerRecord(BaseModel):
    provider_player_id: int
    name: str
    age: int | None = None
    squad_number: int | None = None
    position: str | None = None
    photo_url: str | None = None
