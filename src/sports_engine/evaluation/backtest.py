import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


@dataclass(frozen=True, slots=True)
class BacktestResult:
    predictions_seen: int
    decisions_written: int
    bets: int
    profit: float
    roi: float | None
    report_path: Path


def select_value_decision(
    probabilities: dict[str, float],
    fair_probabilities: dict[str, float],
    decimal_odds: dict[str, float],
    *,
    minimum_probability_difference: float,
    minimum_expected_value: float,
) -> tuple[str, float, float] | None:
    candidates = []
    for outcome in ("home", "draw", "away"):
        if outcome not in fair_probabilities or outcome not in decimal_odds:
            continue
        difference = probabilities[outcome] - fair_probabilities[outcome]
        expected_value = probabilities[outcome] * decimal_odds[outcome] - 1
        if difference >= minimum_probability_difference and expected_value >= minimum_expected_value:
            candidates.append((outcome, decimal_odds[outcome], expected_value))
    return max(candidates, key=lambda item: item[2]) if candidates else None


class BacktestService:
    def __init__(self, connection: duckdb.DuckDBPyConnection, output_dir: Path) -> None:
        self.connection = connection
        self.output_dir = output_dir

    def run(
        self,
        *,
        all_models: bool = False,
        minimum_probability_difference: float = 0.03,
        minimum_expected_value: float = 0.0,
    ) -> BacktestResult:
        status_clause = "" if all_models else "AND mr.status='champion'"
        rows = self.connection.execute(
            "SELECT CAST(p.fixture_id AS VARCHAR), pr.prediction_timestamp, pr.model_version, "
            "p.probability_home, p.probability_draw, p.probability_away, "
            "p.market_home_fair, p.market_draw_fair, p.market_away_fair, "
            "f.home_goals, f.away_goals FROM predictions p "
            "JOIN prediction_runs pr USING (prediction_run_id) "
            "JOIN model_runs mr ON mr.version=pr.model_version "
            "JOIN fixtures_current f USING (fixture_id) "
            f"WHERE f.status_short IN ('FT', 'AET', 'PEN') {status_clause} "
            "ORDER BY pr.prediction_timestamp"
        ).fetchall()
        written = bets = 0
        profit = 0.0
        rule = f"probability_difference>={minimum_probability_difference};expected_value>={minimum_expected_value}"
        for row in rows:
            fixture_id, prediction_time, model_version = row[:3]
            probabilities = dict(zip(("home", "draw", "away"), row[3:6], strict=True))
            market = dict(zip(("home", "draw", "away"), row[6:9], strict=True))
            if any(value is None for value in market.values()):
                continue
            odds = self._odds(fixture_id, prediction_time)
            decision = select_value_decision(
                probabilities,
                market,
                odds,
                minimum_probability_difference=minimum_probability_difference,
                minimum_expected_value=minimum_expected_value,
            )
            actual = "home" if row[9] > row[10] else "draw" if row[9] == row[10] else "away"
            selected, price, _ = decision if decision else (None, None, None)
            pnl = (price - 1 if selected == actual else -1.0) if selected and price else None
            decision_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"sports-engine:backtest:{fixture_id}:{prediction_time}:{model_version}:{rule}",
            )
            changed = self.connection.execute(
                "INSERT INTO backtest_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (decision_id) DO NOTHING RETURNING decision_id",
                [
                    decision_id,
                    fixture_id,
                    prediction_time,
                    self._odds_snapshot_time(fixture_id, prediction_time),
                    model_version,
                    json.dumps(probabilities),
                    json.dumps(market),
                    rule,
                    selected,
                    price,
                    actual,
                    pnl,
                ],
            ).fetchone()
            if changed:
                written += 1
                if pnl is not None:
                    bets += 1
                    profit += pnl
        roi = profit / bets if bets else None
        payload: dict[str, Any] = {
            "created_at": datetime.now(UTC).isoformat(),
            "predictions_seen": len(rows),
            "decisions_written": written,
            "bets": bets,
            "profit": profit,
            "roi": roi,
            "decision_rule": rule,
            "all_models": all_models,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"backtest-{digest}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return BacktestResult(len(rows), written, bets, profit, roi, path)

    def _odds_snapshot_time(self, fixture_id: str, prediction_time: datetime) -> datetime | None:
        row = self.connection.execute(
            "SELECT max(observed_at) FROM odds_snapshots WHERE fixture_id=? AND observed_at<=?",
            [fixture_id, prediction_time],
        ).fetchone()
        return row[0] if row else None

    def _odds(self, fixture_id: str, prediction_time: datetime) -> dict[str, float]:
        snapshot_time = self._odds_snapshot_time(fixture_id, prediction_time)
        if snapshot_time is None:
            return {}
        rows = self.connection.execute(
            "SELECT s.normalized_name, max(p.decimal_odds) FROM odds_snapshots o "
            "JOIN odds_prices p USING (snapshot_id) JOIN bet_markets m USING (market_id) "
            "JOIN bet_selections s USING (selection_id) "
            "WHERE o.fixture_id=? AND o.observed_at=? AND lower(m.name) IN ('match winner', '1x2') "
            "GROUP BY s.normalized_name",
            [fixture_id, snapshot_time],
        ).fetchall()
        return {str(name): float(price) for name, price in rows}
