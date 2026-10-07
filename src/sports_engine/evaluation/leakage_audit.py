from datetime import datetime

from sports_engine.core.exceptions import LeakageError

POST_MATCH_FEATURE_TOKENS = frozenset(
    {"final_score", "match_shots", "match_corners", "postmatch_rating", "actual_result"}
)


def audit_feature_names(feature_names: list[str]) -> None:
    offenders = sorted(
        name for name in feature_names if any(token in name.lower() for token in POST_MATCH_FEATURE_TOKENS)
    )
    if offenders:
        raise LeakageError(f"Post-match feature names found: {offenders}")


def audit_observation_times(prediction_times: list[datetime], source_observation_times: list[datetime]) -> None:
    if len(prediction_times) != len(source_observation_times):
        raise ValueError("Timestamp lists differ in length")
    offenders = [
        index
        for index, pair in enumerate(zip(prediction_times, source_observation_times, strict=True))
        if pair[1] > pair[0]
    ]
    if offenders:
        raise LeakageError(f"Future observations found in rows: {offenders[:20]}")


def audit_temporal_partitions(
    train_times: list[datetime],
    validation_times: list[datetime],
    test_times: list[datetime],
) -> None:
    if not train_times or not validation_times or not test_times:
        raise LeakageError("Temporal partitions must all be non-empty")
    if max(train_times) >= min(validation_times) or max(validation_times) >= min(test_times):
        raise LeakageError("Chronological partitions overlap or are out of order")
    train_set = set(train_times)
    validation_set = set(validation_times)
    test_set = set(test_times)
    if train_set & validation_set or train_set & test_set or validation_set & test_set:
        raise LeakageError("Observation timestamps overlap across temporal partitions")


def audit_transformer_fit_times(fit_times: list[datetime], validation_start: datetime) -> None:
    offenders = [stamp for stamp in fit_times if stamp >= validation_start]
    if offenders:
        raise LeakageError("A fitted transformer or encoder observed validation/future rows")
