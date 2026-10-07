from dataclasses import dataclass

from sports_engine.core.config import Environment
from sports_engine.core.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class ApiFootballCredentials:
    api_key: str
    base_url: str

    @classmethod
    def from_environment(cls) -> "ApiFootballCredentials":
        environment = Environment()
        if not environment.api_football_key:
            raise ConfigurationError("API_FOOTBALL_KEY is not configured")
        return cls(environment.api_football_key, environment.api_football_base_url.rstrip("/"))

    @property
    def headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}
