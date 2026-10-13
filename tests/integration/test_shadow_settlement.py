from datetime import UTC, datetime

from sports_engine.training.feedback import _closing_reference_odds, _upsert_performance_rollup
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def test_closing_reference_query_uses_persisted_effective_timestamp_columns(tmp_path) -> None:
    connection = connect(tmp_path / "closing-reference.duckdb")
    migrate(connection)

    result = _closing_reference_odds(
        connection,
        fixture_id="00000000-0000-0000-0000-000000000001",
        market="MATCH_ODDS",
        selection="HOME",
        line_key="",
        kickoff=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result is None
    connection.close()


def test_performance_rollup_insert_names_the_21_column_schema(tmp_path) -> None:
    connection = connect(tmp_path / "performance-rollup.duckdb")
    migrate(connection)
    now = datetime(2026, 1, 31, tzinfo=UTC)

    _upsert_performance_rollup(
        connection,
        version="model-v1",
        engine="fundamental",
        competition_id="00000000-0000-0000-0000-000000000001",
        market="MATCH_ODDS",
        period_start=now.date().replace(day=1),
        period_end=now.date(),
        sample_size=10,
        log_loss=1.01,
        brier=0.61,
        accuracy=0.5,
        computed_at=now,
    )

    assert connection.execute(
        "SELECT sample_size, log_loss, brier, accuracy FROM model_performance_rollups"
    ).fetchone() == (10, 1.01, 0.61, 0.5)
    connection.close()
