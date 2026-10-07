from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Paging(BaseModel):
    current: int = Field(ge=1)
    total: int = Field(ge=1)


class ApiEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")
    get: str
    parameters: dict[str, Any]
    errors: list[Any] | dict[str, Any]
    results: int = Field(ge=0)
    paging: Paging
    response: list[dict[str, Any]]

    @field_validator("errors")
    @classmethod
    def validate_errors_shape(cls, value: list[Any] | dict[str, Any]) -> list[Any] | dict[str, Any]:
        if not isinstance(value, (list, dict)):
            raise ValueError("API errors must be an object or array")
        return value

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @model_validator(mode="after")
    def validate_result_count(self) -> "ApiEnvelope":
        if self.results != len(self.response):
            raise ValueError("API results does not match response length")
        return self


class ApiStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    account: dict[str, Any]
    subscription: dict[str, Any]
    requests: dict[str, Any]


class ApiStatusEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")
    get: str
    parameters: list[Any] | dict[str, Any]
    errors: list[Any] | dict[str, Any]
    results: int = Field(ge=0)
    response: ApiStatusResponse

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


class CoverageFixtures(BaseModel):
    events: bool = False
    lineups: bool = False
    statistics_fixtures: bool = False
    statistics_players: bool = False


class Coverage(BaseModel):
    fixtures: CoverageFixtures
    standings: bool = False
    players: bool = False
    injuries: bool = False
    predictions: bool = False
    odds: bool = False
