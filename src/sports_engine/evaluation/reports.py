import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl

from sports_engine.evaluation.bookmaker_baseline import bookmaker_baseline_metrics
from sports_engine.evaluation.metrics import probability_metrics
from sports_engine.models.ml.catboost import CatBoostProbabilityModel
from sports_engine.models.ml.lightgbm import LightGBMProbabilityModel
from sports_engine.models.ml.logistic import LogisticProbabilityModel
from sports_engine.models.registry import validate_model_type
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.elo import EloModel
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.training.dataset_builder import load_training_dataset, prediction_times
from sports_engine.training.trainer import NON_FEATURE_COLUMNS, TARGET_LABELS
from sports_engine.training.walk_forward import walk_forward_splits


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    model_type: str
    dataset_id: str
    dataset_hash: str
    fold_metrics: list[dict[str, Any]]
    aggregate_metrics: dict[str, Any]
    created_at: datetime
    path: Path


class WalkForwardEvaluator:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        output_dir: Path,
        *,
        random_seed: int,
        cpu_threads: int,
        time_decay_half_life_days: float = 365.0,
    ) -> None:
        self.connection = connection
        self.output_dir = output_dir
        self.random_seed = random_seed
        self.cpu_threads = cpu_threads
        self.time_decay_half_life_days = time_decay_half_life_days

    def evaluate(
        self,
        model_type: str,
        *,
        dataset_name: str | None = None,
        minimum_train_periods: int | None = None,
        test_periods: int | None = None,
        rolling_train_periods: int | None = None,
    ) -> EvaluationReport:
        validate_model_type(model_type)
        dataset = load_training_dataset(self.connection, dataset_name)
        times = prediction_times(dataset)
        distinct = len(set(times))
        minimum = minimum_train_periods or max(3, int(distinct * 0.6))
        test_size = test_periods or max(1, int(distinct * 0.1))
        folds = walk_forward_splits(
            times,
            minimum_train_periods=minimum,
            test_periods=test_size,
            rolling_train_periods=rolling_train_periods,
        )
        targets = np.asarray([TARGET_LABELS[value] for value in dataset.frame["target_result"]])
        all_targets: list[np.ndarray] = []
        all_probabilities: list[np.ndarray] = []
        all_test_indexes: list[np.ndarray] = []
        fold_metrics: list[dict[str, Any]] = []
        for fold in folds:
            probabilities = self._fit_predict(model_type, dataset.frame, fold.train, fold.test)
            observed = targets[fold.test]
            metrics = probability_metrics(observed, probabilities)
            fold_metrics.append(metrics)
            all_targets.append(observed)
            all_probabilities.append(probabilities)
            all_test_indexes.append(fold.test)
        combined_targets = np.concatenate(all_targets)
        combined_probabilities = np.vstack(all_probabilities)
        aggregate: dict[str, Any] = probability_metrics(combined_targets, combined_probabilities)
        aggregate["folds"] = len(folds)
        aggregate["test_rows"] = len(combined_targets)
        baseline = self._baseline(dataset.frame, np.concatenate(all_test_indexes), combined_targets)
        if baseline is not None:
            aggregate["bookmaker_baseline"] = baseline
            market = self._market_matrix(dataset.frame, np.concatenate(all_test_indexes))
            usable = np.isfinite(market).all(axis=1) & (market.sum(axis=1) > 0)
            normalized = market[usable] / market[usable].sum(axis=1, keepdims=True)
            aggregate["mean_absolute_probability_delta"] = float(
                np.mean(np.abs(combined_probabilities[usable] - normalized))
            )
        closing = self._closing_baseline(dataset.frame, np.concatenate(all_test_indexes), combined_targets)
        if closing is not None:
            aggregate["closing_market"] = closing
        created_at = datetime.now(UTC)
        payload = {
            "model_type": model_type,
            "dataset_id": dataset.dataset_id,
            "dataset_hash": dataset.dataset_hash,
            "fold_metrics": fold_metrics,
            "aggregate_metrics": aggregate,
            "created_at": created_at.isoformat(),
            "minimum_train_periods": minimum,
            "test_periods": test_size,
            "rolling_train_periods": rolling_train_periods,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{model_type}-{dataset.dataset_hash[:12]}-{digest}.json"
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return EvaluationReport(
            model_type,
            dataset.dataset_id,
            dataset.dataset_hash,
            fold_metrics,
            aggregate,
            created_at,
            path,
        )

    def _fit_predict(self, model_type: str, frame: pl.DataFrame, train: np.ndarray, test: np.ndarray) -> np.ndarray:
        if model_type in {"elo", "poisson", "dixon-coles"}:
            matches = list(
                zip(
                    frame["home_team_id"].cast(pl.String).to_list(),
                    frame["away_team_id"].cast(pl.String).to_list(),
                    frame["target_home_goals"].cast(pl.Int64).to_list(),
                    frame["target_away_goals"].cast(pl.Int64).to_list(),
                    strict=True,
                )
            )
            model: Any
            if model_type == "elo":
                model = EloModel()
            elif model_type == "poisson":
                model = PoissonModel()
            else:
                model = DixonColesModel()
            if model_type in {"poisson", "dixon-coles"}:
                timestamps = frame["prediction_timestamp"].to_list()
                model.fit_timed(
                    [(*matches[index], timestamps[index]) for index in train],
                    half_life_days=self.time_decay_half_life_days,
                )
            else:
                model.fit([matches[index] for index in train])
            return model.predict_proba([(matches[index][0], matches[index][1]) for index in test])
        columns = [
            name
            for name, dtype in frame.schema.items()
            if name not in NON_FEATURE_COLUMNS and (dtype.is_numeric() or dtype == pl.Boolean)
        ]
        matrix = frame.select(columns).cast(pl.Float64).to_numpy()
        targets = np.asarray([TARGET_LABELS[value] for value in frame["target_result"]])
        if model_type == "logistic":
            model = LogisticProbabilityModel(random_seed=self.random_seed)
        elif model_type == "catboost":
            model = CatBoostProbabilityModel(random_seed=self.random_seed, threads=self.cpu_threads, iterations=100)
        else:
            model = LightGBMProbabilityModel(random_seed=self.random_seed, threads=self.cpu_threads, n_estimators=100)
        model.fit(matrix[train], targets[train])
        probabilities = np.asarray(model.predict_proba(matrix[test]))
        ordered = np.zeros((len(test), 3))
        for source, target in enumerate(np.asarray(model.estimator.classes_, dtype=int)):
            ordered[:, target] = probabilities[:, source]
        return ordered

    @staticmethod
    def _baseline(frame: pl.DataFrame, indexes: np.ndarray, targets: np.ndarray) -> dict[str, object] | None:
        columns = ("bookmaker_home_fair", "bookmaker_draw_fair", "bookmaker_away_fair")
        if not set(columns) <= set(frame.columns):
            return None
        return bookmaker_baseline_metrics(
            targets,
            frame[columns[0]].cast(pl.Float64).to_numpy()[indexes],
            frame[columns[1]].cast(pl.Float64).to_numpy()[indexes],
            frame[columns[2]].cast(pl.Float64).to_numpy()[indexes],
        )

    @staticmethod
    def _market_matrix(frame: pl.DataFrame, indexes: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [
                frame[column].cast(pl.Float64).to_numpy()[indexes]
                for column in (
                    "bookmaker_home_fair",
                    "bookmaker_draw_fair",
                    "bookmaker_away_fair",
                )
            ]
        )

    def _closing_baseline(
        self, frame: pl.DataFrame, indexes: np.ndarray, targets: np.ndarray
    ) -> dict[str, object] | None:
        observed_targets: list[int] = []
        probability_rows: list[list[float]] = []
        for target, index in zip(targets, indexes, strict=True):
            rows = self.connection.execute(
                "WITH latest AS (SELECT o.snapshot_id FROM odds_snapshots o "
                "JOIN fixtures_current f USING (fixture_id) WHERE o.fixture_id=? "
                "AND o.observed_at<=f.kickoff_utc ORDER BY o.observed_at DESC LIMIT 1) "
                "SELECT s.normalized_name, avg(p.fair_probability) FROM latest l "
                "JOIN odds_prices p USING (snapshot_id) JOIN bet_markets m USING (market_id) "
                "JOIN bet_selections s USING (selection_id) "
                "WHERE lower(m.name) IN ('match winner', '1x2') GROUP BY s.normalized_name",
                [frame["fixture_id"][int(index)]],
            ).fetchall()
            values = {name: value for name, value in rows}
            if not all(values.get(outcome) is not None for outcome in ("home", "draw", "away")):
                continue
            probability_rows.append([float(values[outcome]) for outcome in ("home", "draw", "away")])
            observed_targets.append(int(target))
        if not probability_rows:
            return None
        probabilities = np.asarray(probability_rows)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return {
            **probability_metrics(np.asarray(observed_targets), probabilities),
            "rows": len(observed_targets),
        }
