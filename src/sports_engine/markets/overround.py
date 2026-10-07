from sports_engine.markets.implied_probability import raw_implied_probability


def overround(decimal_odds: list[float]) -> float:
    if len(decimal_odds) < 2:
        raise ValueError("A mutually exclusive market needs at least two prices")
    return sum(raw_implied_probability(value) for value in decimal_odds)
