import json
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


@dataclass(frozen=True, slots=True)
class ShadowSettlementResult:
    opportunities_settled: int


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


def settle_shadow_opportunities(connection: duckdb.DuckDBPyConnection) -> ShadowSettlementResult:
    """Settle the governed paper ledger without mutating its entry-time evidence."""
    rows = connection.execute(
        "SELECT s.shadow_id, o.canonical_market, o.selection, o.line_key, "
        "o.latest_reference_odds, o.minimum_acceptable_odds, f.home_goals, f.away_goals, "
        "CAST(f.fixture_id AS VARCHAR), f.kickoff_utc FROM shadow_opportunities s "
        "JOIN institutional_opportunities o USING (opportunity_id) "
        "JOIN institutional_predictions ip USING (prediction_id) "
        "JOIN fixtures_current f ON f.fixture_id=ip.target_fixture_id "
        "WHERE s.state='SHADOW_ACTIONABLE' AND f.status_short IN ('FT','AET','PEN') "
        "AND f.home_goals IS NOT NULL AND f.away_goals IS NOT NULL "
        "AND o.latest_reference_odds IS NOT NULL"
    ).fetchall()
    settled_at = datetime.now(UTC)
    for shadow_id, market, selection, line_key, odds, minimum, home, away, fixture_id, kickoff in rows:
        unit_return, outcome = _realized_shadow_return(
            str(market),
            str(selection),
            str(line_key),
            float(odds),
            int(home),
            int(away),
        )
        closing = connection.execute(
            "SELECT r.decimal_odds FROM market_reference_quotes r "
            "JOIN institutional_predictions ip ON ip.prediction_id=r.prediction_id "
            "WHERE CAST(ip.target_fixture_id AS VARCHAR)=? AND r.canonical_market=? "
            "AND r.selection=? AND r.line_key=? AND r.reference_observed_at<? "
            "ORDER BY r.reference_observed_at DESC LIMIT 1",
            [fixture_id, market, selection, line_key, kickoff],
        ).fetchone()
        closing_odds = float(closing[0]) if closing and closing[0] is not None else None
        metrics = {
            "outcome": outcome,
            "home_goals": int(home),
            "away_goals": int(away),
            "entry_reference_odds": float(odds),
            "minimum_odds_survived": minimum is not None and float(odds) >= float(minimum),
            "simulated_unit_return": unit_return,
            "closing_reference_odds": closing_odds,
            "closing_odds_movement": closing_odds - float(odds) if closing_odds is not None else None,
            "settlement_version": "shadow-v1",
        }
        connection.execute(
            "UPDATE shadow_opportunities SET state='SHADOW_SETTLED', outcome_metrics=?, settled_at=? "
            "WHERE shadow_id=? AND state='SHADOW_ACTIONABLE'",
            [json.dumps(metrics, sort_keys=True), settled_at, shadow_id],
        )
    return ShadowSettlementResult(len(rows))


def _realized_shadow_return(
    market: str,
    selection: str,
    line_key: str,
    decimal_odds: float,
    home_goals: int,
    away_goals: int,
) -> tuple[float, str]:
    if decimal_odds <= 1:
        raise ValueError("Shadow settlement requires decimal odds greater than one")
    if market == "MATCH_ODDS":
        result = "HOME" if home_goals > away_goals else "DRAW" if home_goals == away_goals else "AWAY"
        return (decimal_odds - 1 if selection == result else -1.0), result
    if market == "BTTS":
        result = "YES" if home_goals > 0 and away_goals > 0 else "NO"
        return (decimal_odds - 1 if selection == result else -1.0), result
    if market == "TOTAL_GOALS":
        line = float(line_key)
        quarter = round(line * 4)
        if not math.isclose(line * 4, quarter, abs_tol=1e-9):
            raise ValueError("Shadow total settlement supports only whole, half, and quarter lines")
        component_lines = [line] if quarter % 2 == 0 else [(quarter - 1) / 4, (quarter + 1) / 4]
        total = home_goals + away_goals
        component_returns: list[float] = []
        grades: list[str] = []
        for component in component_lines:
            margin = total - component if selection == "OVER" else component - total
            if margin > 1e-12:
                component_returns.append(decimal_odds - 1)
                grades.append("WIN")
            elif margin < -1e-12:
                component_returns.append(-1.0)
                grades.append("LOSS")
            else:
                component_returns.append(0.0)
                grades.append("PUSH")
        return sum(component_returns) / len(component_returns), "/".join(grades)
    raise ValueError(f"Unsupported shadow settlement market: {market}")


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
