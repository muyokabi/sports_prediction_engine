from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True, slots=True)
class TemporalFold:
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray


def split_by_time(
    timestamps: list[datetime], validation_fraction: float = 0.2, test_fraction: float = 0.2
) -> TemporalFold:
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("Fractions must be between zero and one")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("Training fraction must be positive")
    if len(set(timestamps)) < 3:
        raise ValueError("At least three distinct timestamps are required")
    unique = sorted(set(timestamps))
    train_boundary = unique[max(1, int(len(unique) * (1 - validation_fraction - test_fraction))) - 1]
    validation_position = max(2, int(len(unique) * (1 - test_fraction)))
    validation_boundary = unique[min(validation_position, len(unique) - 1) - 1]
    epoch_microseconds = np.asarray([stamp.timestamp() * 1_000_000 for stamp in timestamps])
    order = np.argsort(epoch_microseconds, kind="stable")
    train = np.asarray([index for index in order if timestamps[index] <= train_boundary])
    validation = np.asarray([index for index in order if train_boundary < timestamps[index] <= validation_boundary])
    test = np.asarray([index for index in order if timestamps[index] > validation_boundary])
    if not len(train) or not len(validation) or not len(test):
        raise ValueError("Not enough observations for three non-empty temporal partitions")
    return TemporalFold(train, validation, test)
