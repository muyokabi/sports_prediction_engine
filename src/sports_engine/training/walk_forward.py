from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    train: np.ndarray
    test: np.ndarray


def walk_forward_splits(
    timestamps: list[datetime],
    *,
    minimum_train_periods: int,
    test_periods: int,
    step_periods: int | None = None,
    rolling_train_periods: int | None = None,
) -> list[WalkForwardFold]:
    if minimum_train_periods < 1 or test_periods < 1:
        raise ValueError("Training and test period counts must be positive")
    step = step_periods or test_periods
    if step < 1:
        raise ValueError("step_periods must be positive")
    unique = sorted(set(timestamps))
    folds: list[WalkForwardFold] = []
    test_start = minimum_train_periods
    while test_start + test_periods <= len(unique):
        train_start = 0 if rolling_train_periods is None else max(0, test_start - rolling_train_periods)
        train_times = set(unique[train_start:test_start])
        test_times = set(unique[test_start : test_start + test_periods])
        train = np.asarray([index for index, stamp in enumerate(timestamps) if stamp in train_times])
        test = np.asarray([index for index, stamp in enumerate(timestamps) if stamp in test_times])
        folds.append(WalkForwardFold(train, test))
        test_start += step
    if not folds:
        raise ValueError("Not enough distinct timestamps for a walk-forward fold")
    return folds
