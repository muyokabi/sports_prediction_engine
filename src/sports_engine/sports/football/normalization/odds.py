import re
from typing import Any

from sports_engine.sports.football.domain.odds import OddsPrice

LINE_PATTERN = re.compile(r"^(?P<name>Over|Under)\s+(?P<line>[+-]?\d+(?:\.\d+)?)$", re.IGNORECASE)
HANDICAP_PATTERN = re.compile(r"^(?P<name>.+?)\s+(?P<line>[+-]\d+(?:\.\d+)?)$")


def normalize_odds(payload: dict[str, Any]) -> list[OddsPrice]:
    fixture_id = payload["fixture"]["id"]
    update = payload.get("update")
    prices: list[OddsPrice] = []
    for bookmaker in payload.get("bookmakers", []):
        for market in bookmaker.get("bets", []):
            for selection in market.get("values", []):
                try:
                    decimal_odds = float(selection["odd"])
                except (KeyError, TypeError, ValueError):
                    continue
                if decimal_odds <= 1:
                    continue
                raw_name = str(selection["value"])
                match = LINE_PATTERN.match(raw_name.strip())
                if match is None and "handicap" in str(market.get("name", "")).lower():
                    match = HANDICAP_PATTERN.match(raw_name.strip())
                line = match.group("line") if match else None
                selection_name = match.group("name") if match else raw_name
                prices.append(
                    OddsPrice(
                        provider_fixture_id=fixture_id,
                        provider_bookmaker_id=bookmaker["id"],
                        bookmaker_name=bookmaker["name"],
                        provider_market_id=market["id"],
                        market_name=market["name"],
                        selection_name=selection_name,
                        line=line,
                        decimal_odds=decimal_odds,
                        provider_update_time=update,
                    )
                )
    return prices
