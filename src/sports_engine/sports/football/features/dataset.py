import hashlib
import json
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any

import duckdb
import polars as pl

from sports_engine.evaluation.leakage_audit import audit_feature_names, audit_observation_times


@dataclass(frozen=True, slots=True)
class FeatureDatasetArtifact:
    dataset_id: str
    row_count: int
    parquet_path: Path
    schema_hash: str
    dataset_hash: str


class PointInTimeFeatureBuilder:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        output_dir: Path,
        *,
        windows: list[int],
        exponential_half_life: float,
        prediction_lead_hours: int,
    ) -> None:
        if not windows or any(window < 1 for window in windows):
            raise ValueError("At least one positive feature window is required")
        self.connection = connection
        self.output_dir = output_dir
        self.windows = sorted(set(windows))
        self.half_life = exponential_half_life
        self.prediction_lead = timedelta(hours=prediction_lead_hours)

    def build(self, name: str, *, ledger_mode: str) -> FeatureDatasetArtifact:
        matches = self._matches(ledger_mode)
        if not matches:
            raise ValueError(f"No ML-eligible {ledger_mode} fixtures are available")
        histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
        ratings: dict[str, float] = defaultdict(lambda: 1500.0)
        pending_elo: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        source_times: list[datetime] = []
        prediction_times: list[datetime] = []
        for match in matches:
            prediction_time = match["kickoff_utc"] - self.prediction_lead
            for prior in list(pending_elo):
                if prior["source_observed_at"] <= prediction_time:
                    self._update_elo(ratings, prior)
                    pending_elo.remove(prior)
            home_history = [
                item for item in histories[match["home_team_id"]] if item["source_observed_at"] <= prediction_time
            ]
            away_history = [
                item for item in histories[match["away_team_id"]] if item["source_observed_at"] <= prediction_time
            ]
            known_sources = [item["source_observed_at"] for item in home_history + away_history]
            source_max = max(known_sources, default=prediction_time)
            row: dict[str, Any] = {
                "fixture_id": match["fixture_id"],
                "prediction_timestamp": prediction_time,
                "home_team_id": match["home_team_id"],
                "away_team_id": match["away_team_id"],
                "source_observation_max": source_max,
                "home_elo": ratings[match["home_team_id"]],
                "away_elo": ratings[match["away_team_id"]],
                "elo_difference": ratings[match["home_team_id"]] - ratings[match["away_team_id"]],
                "home_history_matches": len(home_history),
                "away_history_matches": len(away_history),
                "target_home_goals": match["home_goals"],
                "target_away_goals": match["away_goals"],
                "target_result": self._result(match["home_goals"], match["away_goals"]),
            }
            row.update(self._team_features("home", home_history, match["kickoff_utc"], "HOME"))
            row.update(self._team_features("away", away_history, match["kickoff_utc"], "AWAY"))
            home_gd = self._average(home_history, "goal_difference")
            away_gd = self._average(away_history, "goal_difference")
            row["home_opponent_adjusted_goal_difference"] = (
                home_gd - away_gd if home_gd is not None and away_gd is not None else None
            )
            row["away_opponent_adjusted_goal_difference"] = (
                away_gd - home_gd if home_gd is not None and away_gd is not None else None
            )
            row.update(self._odds_features(match["fixture_id"], prediction_time))
            row.update(self._availability_features(match, prediction_time))
            row.update(self._lineup_features(match, prediction_time))
            rows.append(row)
            prediction_times.append(prediction_time)
            source_times.append(source_max)
            for team_id, opponent_id, venue, goals_for, goals_against, stats in (
                (
                    match["home_team_id"],
                    match["away_team_id"],
                    "HOME",
                    match["home_goals"],
                    match["away_goals"],
                    match["home_stats"],
                ),
                (
                    match["away_team_id"],
                    match["home_team_id"],
                    "AWAY",
                    match["away_goals"],
                    match["home_goals"],
                    match["away_stats"],
                ),
            ):
                histories[team_id].append(
                    {
                        "opponent_team_id": opponent_id,
                        "venue": venue,
                        "kickoff_utc": match["kickoff_utc"],
                        "source_observed_at": match["source_observed_at"],
                        "goals_for": goals_for,
                        "goals_against": goals_against,
                        "goal_difference": goals_for - goals_against,
                        "points": 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0,
                        **stats,
                    }
                )
            pending_elo.append(match)
        audit_observation_times(prediction_times, source_times)
        frame = pl.DataFrame(rows)
        feature_names = [
            name
            for name in frame.columns
            if not name.startswith("target_")
            and name
            not in {
                "fixture_id",
                "prediction_timestamp",
                "home_team_id",
                "away_team_id",
                "source_observation_max",
            }
        ]
        audit_feature_names(feature_names)
        return self._write(name, ledger_mode, frame)

    def build_prediction_frame(
        self,
        target_date: datetime,
        *,
        ledger_mode: str,
        observed_at: datetime,
        timezone: str,
    ) -> pl.DataFrame:
        targets = self.connection.execute(
            "SELECT CAST(f.fixture_id AS VARCHAR), f.kickoff_utc, "
            "CAST(f.home_team_id AS VARCHAR), CAST(f.away_team_id AS VARCHAR), "
            "c.name, ht.name, awt.name "
            "FROM fixtures_current f JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) JOIN teams ht ON ht.team_id=f.home_team_id "
            "JOIN teams awt ON awt.team_id=f.away_team_id "
            "WHERE cs.ledger_mode=? AND CAST(timezone(?, f.kickoff_utc) AS DATE)=CAST(? AS DATE) "
            "AND f.kickoff_utc>? AND f.status_short IN ('NS', 'TBD') ORDER BY f.kickoff_utc",
            [ledger_mode, timezone, target_date, observed_at],
        ).fetchall()
        if not targets:
            return pl.DataFrame()
        completed = self._matches(ledger_mode)
        rows: list[dict[str, Any]] = []
        for fixture_id, kickoff, home_team, away_team, competition, home_name, away_name in targets:
            prediction_time = observed_at
            eligible_history = [
                match
                for match in completed
                if match["source_observed_at"] <= prediction_time and match["kickoff_utc"] < kickoff
            ]
            histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
            ratings: dict[str, float] = defaultdict(lambda: 1500.0)
            for match in eligible_history:
                self._update_elo(ratings, match)
                for team_id, opponent_id, venue, goals_for, goals_against, stats in (
                    (
                        match["home_team_id"],
                        match["away_team_id"],
                        "HOME",
                        match["home_goals"],
                        match["away_goals"],
                        match["home_stats"],
                    ),
                    (
                        match["away_team_id"],
                        match["home_team_id"],
                        "AWAY",
                        match["away_goals"],
                        match["home_goals"],
                        match["away_stats"],
                    ),
                ):
                    histories[team_id].append(
                        {
                            "opponent_team_id": opponent_id,
                            "venue": venue,
                            "kickoff_utc": match["kickoff_utc"],
                            "source_observed_at": match["source_observed_at"],
                            "goals_for": goals_for,
                            "goals_against": goals_against,
                            "goal_difference": goals_for - goals_against,
                            "points": 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0,
                            **stats,
                        }
                    )
            home_history = histories[home_team]
            away_history = histories[away_team]
            known_sources = [item["source_observed_at"] for item in home_history + away_history]
            match = {
                "fixture_id": fixture_id,
                "kickoff_utc": kickoff,
                "home_team_id": home_team,
                "away_team_id": away_team,
                "competition": competition,
                "home_team_name": home_name,
                "away_team_name": away_name,
            }
            row: dict[str, Any] = {
                "fixture_id": fixture_id,
                "kickoff_utc": kickoff,
                "competition": competition,
                "home_team_name": home_name,
                "away_team_name": away_name,
                "prediction_timestamp": prediction_time,
                "home_team_id": home_team,
                "away_team_id": away_team,
                "source_observation_max": max(known_sources, default=prediction_time),
                "home_elo": ratings[home_team],
                "away_elo": ratings[away_team],
                "elo_difference": ratings[home_team] - ratings[away_team],
                "home_history_matches": len(home_history),
                "away_history_matches": len(away_history),
            }
            row.update(self._team_features("home", home_history, kickoff, "HOME"))
            row.update(self._team_features("away", away_history, kickoff, "AWAY"))
            home_gd = self._average(home_history, "goal_difference")
            away_gd = self._average(away_history, "goal_difference")
            row["home_opponent_adjusted_goal_difference"] = (
                home_gd - away_gd if home_gd is not None and away_gd is not None else None
            )
            row["away_opponent_adjusted_goal_difference"] = (
                away_gd - home_gd if home_gd is not None and away_gd is not None else None
            )
            row.update(self._odds_features(fixture_id, prediction_time))
            row.update(self._availability_features(match, prediction_time))
            row.update(self._lineup_features(match, prediction_time))
            rows.append(row)
        frame = pl.DataFrame(rows)
        audit_observation_times(frame["prediction_timestamp"].to_list(), frame["source_observation_max"].to_list())
        return frame

    def _matches(self, ledger_mode: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT CAST(f.fixture_id AS VARCHAR), f.kickoff_utc, "
            "CAST(f.home_team_id AS VARCHAR), CAST(f.away_team_id AS VARCHAR), "
            "f.home_goals, f.away_goals, greatest(h.retrieved_at, a.retrieved_at), "
            "h.shots_on_goal, h.total_shots, h.corner_kicks, h.ball_possession, h.total_passes, "
            "h.passes_percentage, h.fouls, h.yellow_cards, h.red_cards, "
            "a.shots_on_goal, a.total_shots, a.corner_kicks, a.ball_possession, a.total_passes, "
            "a.passes_percentage, a.fouls, a.yellow_cards, a.red_cards, "
            "hp.player_rating, ap.player_rating "
            "FROM fixtures_current f JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN fixture_quality_status q USING (fixture_id) "
            "JOIN team_match_statistics h ON h.fixture_id=f.fixture_id AND h.team_id=f.home_team_id "
            "JOIN team_match_statistics a ON a.fixture_id=f.fixture_id AND a.team_id=f.away_team_id "
            "LEFT JOIN (SELECT fixture_id, team_id, avg(rating) player_rating FROM player_match_statistics "
            "GROUP BY fixture_id, team_id) hp ON hp.fixture_id=f.fixture_id AND hp.team_id=f.home_team_id "
            "LEFT JOIN (SELECT fixture_id, team_id, avg(rating) player_rating FROM player_match_statistics "
            "GROUP BY fixture_id, team_id) ap ON ap.fixture_id=f.fixture_id AND ap.team_id=f.away_team_id "
            "WHERE cs.ledger_mode=? AND q.eligibility='ML_ELIGIBLE' "
            "AND f.home_goals IS NOT NULL AND f.away_goals IS NOT NULL ORDER BY f.kickoff_utc",
            [ledger_mode],
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "fixture_id": row[0],
                    "kickoff_utc": row[1],
                    "home_team_id": row[2],
                    "away_team_id": row[3],
                    "home_goals": row[4],
                    "away_goals": row[5],
                    "source_observed_at": row[6],
                    "home_stats": self._stats(row[7:16], row[25]),
                    "away_stats": self._stats(row[16:25], row[26]),
                }
            )
        return result

    @staticmethod
    def _stats(values: tuple[Any, ...], player_rating: Any) -> dict[str, Any]:
        names = (
            "shots_on_goal",
            "total_shots",
            "corner_kicks",
            "possession",
            "total_passes",
            "passes_percentage",
            "fouls",
            "yellow_cards",
            "red_cards",
        )
        return {**dict(zip(names, values, strict=False)), "player_rating": player_rating}

    def _team_features(
        self, prefix: str, history: list[dict[str, Any]], kickoff: datetime, venue: str
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        metrics = (
            "points",
            "goals_for",
            "goals_against",
            "goal_difference",
            "shots_on_goal",
            "total_shots",
            "corner_kicks",
            "possession",
            "total_passes",
            "passes_percentage",
            "fouls",
            "yellow_cards",
            "red_cards",
            "player_rating",
        )
        for window in self.windows:
            sample = history[-window:]
            for metric in metrics:
                result[f"{prefix}_{metric}_l{window}"] = self._average(sample, metric)
        for metric in metrics:
            result[f"{prefix}_{metric}_season"] = self._average(history, metric)
            result[f"{prefix}_{metric}_ewm"] = self._ewm(history, metric)
        venue_history = [item for item in history if item["venue"] == venue]
        result[f"{prefix}_venue_goals_for"] = self._average(venue_history, "goals_for")
        result[f"{prefix}_venue_goals_against"] = self._average(venue_history, "goals_against")
        result[f"{prefix}_rest_days"] = (
            (kickoff - history[-1]["kickoff_utc"]).total_seconds() / 86_400 if history else None
        )
        result[f"{prefix}_fixtures_last_14d"] = sum(0 < (kickoff - item["kickoff_utc"]).days <= 14 for item in history)
        return result

    @staticmethod
    def _average(history: list[dict[str, Any]], field: str) -> float | None:
        values = [float(item[field]) for item in history if item.get(field) is not None]
        return fmean(values) if values else None

    def _ewm(self, history: list[dict[str, Any]], field: str) -> float | None:
        values = [float(item[field]) for item in history if item.get(field) is not None]
        if not values:
            return None
        weights = [math.exp(-math.log(2) * (len(values) - 1 - index) / self.half_life) for index in range(len(values))]
        return sum(value * weight for value, weight in zip(values, weights, strict=True)) / sum(weights)

    def _odds_features(self, fixture_id: str, prediction_time: datetime) -> dict[str, Any]:
        rows = self.connection.execute(
            "WITH latest AS (SELECT max(observed_at) observed_at FROM odds_snapshots "
            "WHERE fixture_id=? AND observed_at<=?) "
            "SELECT s.normalized_name, avg(p.fair_probability), min(o.observed_at), max(o.observed_at) "
            "FROM odds_snapshots o JOIN latest l USING (observed_at) JOIN odds_prices p USING (snapshot_id) "
            "JOIN bet_markets m USING (market_id) JOIN bet_selections s USING (selection_id) "
            "WHERE o.fixture_id=? AND lower(m.name) IN ('match winner', '1x2') "
            "GROUP BY s.normalized_name",
            [fixture_id, prediction_time, fixture_id],
        ).fetchall()
        values = {row[0]: row[1] for row in rows}
        return {
            "bookmaker_home_fair": values.get("home"),
            "bookmaker_draw_fair": values.get("draw"),
            "bookmaker_away_fair": values.get("away"),
            "bookmaker_consensus_known": bool(rows),
            "odds_movement_known": any(row[2] != row[3] for row in rows),
        }

    def _availability_features(self, match: dict[str, Any], prediction_time: datetime) -> dict[str, Any]:
        collection = self.connection.execute(
            "SELECT count(*) FROM injury_collection_runs WHERE target_date=CAST(? AS DATE) "
            "AND observed_at<=? AND complete",
            [match["kickoff_utc"], prediction_time],
        ).fetchone()
        known = bool(collection and collection[0])
        result: dict[str, Any] = {"player_availability_known": known}
        for prefix in ("home", "away"):
            team_id = match[f"{prefix}_team_id"]
            injuries = self.connection.execute(
                "SELECT count(DISTINCT player_id) FROM injury_observations "
                "WHERE provider_fixture_id=(SELECT provider_fixture_id FROM fixtures WHERE fixture_id=?) "
                "AND CAST(team_id AS VARCHAR)=? AND observed_at<=?",
                [match["fixture_id"], team_id, prediction_time],
            ).fetchone()
            injured = int(injuries[0]) if injuries else 0
            squad = self.connection.execute(
                "SELECT count(*) FROM squad_players WHERE snapshot_id=("
                "SELECT snapshot_id FROM squad_snapshots WHERE CAST(team_id AS VARCHAR)=? "
                "AND observed_at<=? ORDER BY observed_at DESC LIMIT 1)",
                [team_id, prediction_time],
            ).fetchone()
            squad_size = int(squad[0]) if squad and squad[0] else 0
            result[f"{prefix}_injured_players"] = injured if known else None
            result[f"{prefix}_player_availability"] = 1 - injured / squad_size if known and squad_size else None
        return result

    def _lineup_features(self, match: dict[str, Any], prediction_time: datetime) -> dict[str, Any]:
        strengths: dict[str, float | None] = {}
        known = True
        for prefix in ("home", "away"):
            team_id = match[f"{prefix}_team_id"]
            observation = self.connection.execute(
                "SELECT count(*) FROM lineup_observations lo JOIN lineups l USING (lineup_id) "
                "WHERE l.fixture_id=? AND CAST(l.team_id AS VARCHAR)=? AND lo.observed_at<=?",
                [match["fixture_id"], team_id, prediction_time],
            ).fetchone()
            team_known = bool(observation and observation[0])
            known = known and team_known
            if not team_known:
                strengths[prefix] = None
                continue
            rating = self.connection.execute(
                "SELECT avg(pms.rating) FROM lineup_players lp JOIN lineups l USING (lineup_id) "
                "JOIN player_match_statistics pms ON pms.player_id=lp.player_id "
                "WHERE l.fixture_id=? AND CAST(l.team_id AS VARCHAR)=? AND pms.retrieved_at<=?",
                [match["fixture_id"], team_id, prediction_time],
            ).fetchone()
            strengths[prefix] = float(rating[0]) if rating and rating[0] is not None else None
        return {
            "home_lineup_strength": strengths["home"],
            "away_lineup_strength": strengths["away"],
            "lineup_strength_known": known,
        }

    @staticmethod
    def _update_elo(ratings: dict[str, float], match: dict[str, Any]) -> None:
        home = match["home_team_id"]
        away = match["away_team_id"]
        expected = 1 / (1 + 10 ** ((ratings[away] - ratings[home] - 60) / 400))
        actual = (
            1.0
            if match["home_goals"] > match["away_goals"]
            else 0.5
            if match["home_goals"] == match["away_goals"]
            else 0.0
        )
        change = 20 * (actual - expected)
        ratings[home] += change
        ratings[away] -= change

    @staticmethod
    def _result(home_goals: int, away_goals: int) -> str:
        return "HOME" if home_goals > away_goals else "DRAW" if home_goals == away_goals else "AWAY"

    def _write(self, name: str, ledger_mode: str, frame: pl.DataFrame) -> FeatureDatasetArtifact:
        schema_payload = [(column, str(frame.schema[column])) for column in frame.columns]
        schema_hash = hashlib.sha256(json.dumps(schema_payload).encode()).hexdigest()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.output_dir / f".{name}.{uuid.uuid4().hex}.parquet"
        frame.write_parquet(temporary)
        dataset_hash = hashlib.sha256(temporary.read_bytes()).hexdigest()
        path = self.output_dir / f"{name}-{dataset_hash[:12]}.parquet"
        temporary.replace(path)
        dataset_id = uuid.uuid5(uuid.NAMESPACE_URL, f"sports-engine:{name}:{dataset_hash}")
        prediction_times = frame["prediction_timestamp"].to_list()
        config = {
            "ledger_mode": ledger_mode,
            "windows": self.windows,
            "exponential_half_life": self.half_life,
            "prediction_lead_hours": self.prediction_lead.total_seconds() / 3600,
        }
        self.connection.execute(
            "INSERT INTO feature_datasets VALUES (?, ?, current_timestamp, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (dataset_id) DO NOTHING",
            [
                dataset_id,
                name,
                min(prediction_times),
                max(prediction_times),
                schema_hash,
                dataset_hash,
                str(path),
                json.dumps(config),
            ],
        )
        return FeatureDatasetArtifact(str(dataset_id), frame.height, path, schema_hash, dataset_hash)
