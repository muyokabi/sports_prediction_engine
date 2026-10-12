from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from sports_engine.core.config import ApplicationMode
from sports_engine.training.historical import train_historical_models


class Connection:
    def __init__(self, replay_rows: int) -> None:
        self.replay_rows = replay_rows

    def execute(self, _query: str) -> "Connection":
        return self

    def fetchone(self) -> tuple[int]:
        return (self.replay_rows,)


def _config(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        mode=ApplicationMode.PRODUCTION,
        data_dir=tmp_path / "data",
        artifacts_dir=tmp_path / "artifacts",
        features=SimpleNamespace(windows=[5, 10], exponential_half_life=5.0, prediction_lead_hours=24),
        models=SimpleNamespace(
            historical_training_ledgers=["replay"],
            random_seed=7,
            cpu_threads=1,
            time_decay_half_life_days=365.0,
            promotion=SimpleNamespace(
                minimum_competition_evaluation_rows=100,
                maximum_competition_expected_calibration_error=0.08,
            ),
        ),
    )


def test_historical_training_builds_once_and_full_refits_selected_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {"trained": [], "evaluated": []}

    class Builder:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            calls["history"] = kwargs["historical_ledger_modes"]
            calls["universe_states"] = kwargs["replay_universe_states"]

        def build(self, name: str, *, ledger_mode: str) -> SimpleNamespace:
            calls["dataset"] = (name, ledger_mode)
            return SimpleNamespace(dataset_id="dataset-id", row_count=2400)

    class Trainer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def train(self, model_type: str, **kwargs: object) -> SimpleNamespace:
            calls["trained"].append((model_type, kwargs))  # type: ignore[union-attr]
            return SimpleNamespace(version=f"{model_type}-candidate")

    class Evaluator:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def evaluate(self, model_type: str, **kwargs: object) -> SimpleNamespace:
            calls["evaluated"].append((model_type, kwargs))  # type: ignore[union-attr]
            return SimpleNamespace(path=tmp_path / f"{model_type}.json")

    def promote(*_args: object, **kwargs: object) -> SimpleNamespace:
        calls["promoted"] = kwargs["versions"]
        return SimpleNamespace(promoted_versions=(), withheld_versions=kwargs["versions"])

    def compare(paths: list[Path], output_dir: Path, *, random_seed: int) -> Path:
        calls["compared"] = (paths, output_dir, random_seed)
        return output_dir / "comparison.json"

    monkeypatch.setattr("sports_engine.training.historical.PointInTimeFeatureBuilder", Builder)
    monkeypatch.setattr("sports_engine.training.historical.ModelTrainer", Trainer)
    monkeypatch.setattr("sports_engine.training.historical.WalkForwardEvaluator", Evaluator)
    monkeypatch.setattr("sports_engine.training.historical.run_automated_promotion", promote)
    monkeypatch.setattr("sports_engine.training.historical.compare_evaluation_reports", compare)

    result = train_historical_models(
        Connection(2400),  # type: ignore[arg-type]
        _config(tmp_path),  # type: ignore[arg-type]
        model_types=("elo", "logistic"),
        dataset_name="five-seasons",
        rolling_periods=3,
        now=datetime(2026, 10, 11, tzinfo=UTC),
    )

    assert result.dataset_name == "five-seasons"
    assert result.dataset_rows == 2400
    assert result.replay_rows == 2400
    assert calls["history"] == ["replay"]
    assert calls["universe_states"] == ["ACTIONABLE"]
    assert calls["dataset"] == ("five-seasons", "production")
    assert calls["trained"] == [
        (
            "elo",
            {
                "dataset_name": "five-seasons",
                "calibration_method": None,
                "training_mode": "full_refit",
            },
        ),
        (
            "logistic",
            {
                "dataset_name": "five-seasons",
                "calibration_method": "platt",
                "training_mode": "full_refit",
            },
        ),
    ]
    assert calls["promoted"] == ("elo-candidate", "logistic-candidate")
    assert calls["compared"] == (
        [tmp_path / "elo.json", tmp_path / "logistic.json"],
        tmp_path / "artifacts" / "evaluation" / "comparisons",
        7,
    )
    assert result.comparison_path == tmp_path / "artifacts" / "evaluation" / "comparisons" / "comparison.json"


def test_historical_training_requires_completed_replay_rows(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No completed replay results"):
        train_historical_models(
            Connection(0),  # type: ignore[arg-type]
            _config(tmp_path),  # type: ignore[arg-type]
            model_types=("elo",),
        )
