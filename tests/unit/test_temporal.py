from datetime import UTC, datetime, timedelta

import pytest

from sports_engine.core.exceptions import LeakageError
from sports_engine.evaluation.leakage_audit import (
    audit_feature_names,
    audit_observation_times,
    audit_temporal_partitions,
    audit_transformer_fit_times,
)
from sports_engine.training.temporal_split import split_by_time
from sports_engine.training.walk_forward import walk_forward_splits


def test_temporal_split_never_shuffles() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    stamps = [base + timedelta(days=value) for value in [4, 0, 5, 1, 3, 2, 6, 7, 8, 9]]
    fold = split_by_time(stamps)
    train_times = [stamps[index] for index in fold.train]
    validation_times = [stamps[index] for index in fold.validation]
    test_times = [stamps[index] for index in fold.test]
    assert max(train_times) < min(validation_times) < min(test_times)


def test_temporal_split_keeps_simultaneous_fixtures_in_one_partition() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    stamps = [base + timedelta(days=value) for value in [0, 0, 1, 2, 3, 4, 4]]
    fold = split_by_time(stamps)
    partitions = [fold.train, fold.validation, fold.test]
    locations = [
        partition_index for partition_index, partition in enumerate(partitions) if 0 in partition or 1 in partition
    ]
    assert locations == [0]
    audit_temporal_partitions(
        [stamps[index] for index in fold.train],
        [stamps[index] for index in fold.validation],
        [stamps[index] for index in fold.test],
    )


def test_walk_forward_supports_expanding_and_rolling_windows() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    stamps = [base + timedelta(days=value) for value in range(8)]
    expanding = walk_forward_splits(stamps, minimum_train_periods=4, test_periods=2)
    rolling = walk_forward_splits(stamps, minimum_train_periods=4, test_periods=2, rolling_train_periods=3)
    assert len(expanding) == 2
    assert expanding[1].train.tolist() == [0, 1, 2, 3, 4, 5]
    assert rolling[1].train.tolist() == [3, 4, 5]
    assert rolling[1].test.tolist() == [6, 7]


def test_leakage_audit_rejects_postmatch_names_and_future_observations() -> None:
    with pytest.raises(LeakageError):
        audit_feature_names(["form_l5", "match_shots_home"])
    now = datetime.now(UTC)
    with pytest.raises(LeakageError):
        audit_observation_times([now], [now + timedelta(seconds=1)])


def test_leakage_audit_rejects_partition_overlap_and_future_transformer_fit() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(LeakageError, match="overlap"):
        audit_temporal_partitions(
            [base, base + timedelta(days=2)],
            [base + timedelta(days=1)],
            [base + timedelta(days=3)],
        )
    with pytest.raises(LeakageError, match="transformer"):
        audit_transformer_fit_times(
            [base, base + timedelta(days=2)],
            base + timedelta(days=2),
        )
