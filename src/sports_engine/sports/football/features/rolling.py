import polars as pl


def rolling_team_features(frame: pl.DataFrame, windows: list[int]) -> pl.DataFrame:
    required = {"fixture_id", "team_id", "kickoff_utc", "goals_for", "goals_against"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing team-ledger fields: {sorted(missing)}")
    result = frame.sort(["team_id", "kickoff_utc"])
    for window in windows:
        result = result.with_columns(
            pl.col("goals_for")
            .shift(1)
            .rolling_mean(window_size=window, min_samples=1)
            .over("team_id")
            .alias(f"goals_for_l{window}"),
            pl.col("goals_against")
            .shift(1)
            .rolling_mean(window_size=window, min_samples=1)
            .over("team_id")
            .alias(f"goals_against_l{window}"),
        )
    return result
