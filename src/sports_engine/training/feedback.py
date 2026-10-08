import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb


@dataclass(frozen=True, slots=True)
class SettlementResult:
    predictions_settled: int
    probability_rows: int


def settle_completed_predictions(connection: duckdb.DuckDBPyConnection) -> SettlementResult:
    """Attach final 1X2 outcomes to immutable institutional probabilities idempotently."""
    rows = connection.execute(
        "SELECT ip.prediction_id, e.engine, e.canonical_market, e.selection, e.line_key, "
        "e.model_version, e.probability, f.home_goals, f.away_goals "
        "FROM institutional_predictions ip JOIN fixtures_current f "
        "ON f.fixture_id=ip.target_fixture_id JOIN engine_probability_prices e "
        "ON e.prediction_id=ip.prediction_id LEFT JOIN prediction_outcomes o "
        "ON o.prediction_id=e.prediction_id AND o.engine=e.engine "
        "AND o.canonical_market=e.canonical_market AND o.selection=e.selection "
        "AND o.line_key=e.line_key WHERE o.prediction_id IS NULL "
        "AND f.status_short IN ('FT','AET','PEN') "
        "AND f.home_goals IS NOT NULL AND f.away_goals IS NOT NULL "
        "AND e.canonical_market='MATCH_ODDS' AND e.selection IN ('HOME','DRAW','AWAY') "
        "AND e.probability IS NOT NULL"
    ).fetchall()
    now = datetime.now(UTC)
    prediction_ids: set[str] = set()
    for prediction_id, engine, market, selection, line_key, version, probability, home, away in rows:
        outcome = "HOME" if home > away else "DRAW" if home == away else "AWAY"
        target = 1.0 if selection == outcome else 0.0
        clipped = min(max(float(probability), 1e-15), 1 - 1e-15)
        log_loss = -(target * math.log(clipped) + (1 - target) * math.log(1 - clipped))
        connection.execute(
            "INSERT INTO prediction_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, ?, 'score-v1')",
            [
                prediction_id,
                engine,
                market,
                selection,
                line_key,
                version,
                outcome,
                probability,
                (clipped - target) ** 2,
                now,
            ],
        )
        # The multiclass log-loss is stored only on the realized selection row;
        # per-selection Brier remains available on all three rows.
        if target:
            connection.execute(
                "UPDATE prediction_outcomes SET log_loss=? WHERE prediction_id=? AND engine=? "
                "AND canonical_market=? AND selection=? AND line_key=?",
                [log_loss, prediction_id, engine, market, selection, line_key],
            )
        prediction_ids.add(str(prediction_id))
    return SettlementResult(len(prediction_ids), len(rows))


def record_drift_signal(
    connection: duckdb.DuckDBPyConnection,
    *,
    model_version: str,
    signal_type: str,
    value: float,
    threshold: float,
    due_state: str = "RETRAINING_DUE",
) -> str:
    """Persist an advisory drift signal; this never promotes or mutates a champion."""
    state = due_state if abs(value) >= threshold else "NO_SIGNAL"
    signal_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO model_drift_signals VALUES (?, ?, ?, '{}', ?, ?, ?, '{}', ?)",
        [signal_id, model_version, signal_type, value, threshold, state, datetime.now(UTC)],
    )
    return signal_id


def refresh_performance_rollups(connection: duckdb.DuckDBPyConnection) -> int:
    """Rebuild transparent settled 1X2 model/league/month monitoring summaries."""
    rows = connection.execute(
        "SELECT CAST(o.prediction_id AS VARCHAR), o.model_version, o.engine, "
        "f.competition_season_id, o.canonical_market, o.selection, o.actual_outcome, "
        "o.probability, o.log_loss, o.brier, CAST(date_trunc('month', f.kickoff_utc) AS DATE) "
        "FROM prediction_outcomes o JOIN institutional_predictions ip USING (prediction_id) "
        "JOIN fixtures_current f ON f.fixture_id=ip.target_fixture_id"
    ).fetchall()
    groups: dict[tuple[Any, ...], list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        groups[(row[1], row[2], row[3], row[4], row[10])].append(row)
    written = 0
    for (version, engine, competition_id, market, period), values in groups.items():
        predictions: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for value in values:
            predictions[str(value[0])].append(value)
        sample_size = len(predictions)
        if not sample_size:
            continue
        realized_losses = [float(value[8]) for value in values if value[8] is not None]
        brier_values = [float(value[9]) for value in values if value[9] is not None]
        brier = sum(brier_values) / sample_size
        correct = 0
        for prices in predictions.values():
            best = max(prices, key=lambda item: float(item[7]))
            correct += str(best[5]) == str(best[6])
        period_end_row = connection.execute("SELECT last_day(?)", [period]).fetchone()
        if period_end_row is None:
            continue
        period_end = period_end_row[0]
        connection.execute(
            "INSERT INTO model_performance_rollups VALUES (?, ?, ?, ?, ?, 'ALL', 'ALL', ?, ?, ?, ?, ?, "
            "NULL, NULL, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?) "
            "ON CONFLICT (model_version, engine, competition_id, canonical_market, odds_band, "
            "opportunity_band, period_start, period_end) DO UPDATE SET sample_size=excluded.sample_size, "
            "log_loss=excluded.log_loss, brier=excluded.brier, accuracy=excluded.accuracy, "
            "computed_at=excluded.computed_at",
            [
                str(uuid.uuid4()),
                version,
                engine,
                competition_id,
                market,
                period,
                period_end,
                sample_size,
                sum(realized_losses) / sample_size if realized_losses else None,
                brier,
                correct / sample_size,
                datetime.now(UTC),
            ],
        )
        written += 1
    return written
