from pathlib import Path

from sports_engine.training.feedback import record_drift_signal, settle_completed_predictions
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def test_feedback_is_idempotent_and_drift_is_advisory(tmp_path: Path) -> None:
    connection = connect(tmp_path / "feedback.duckdb")
    migrate(connection)
    assert settle_completed_predictions(connection).probability_rows == 0
    signal_id = record_drift_signal(
        connection,
        model_version="immutable-v1",
        signal_type="calibration",
        value=0.2,
        threshold=0.1,
        due_state="RECALIBRATION_DUE",
    )
    assert connection.execute("SELECT state FROM model_drift_signals WHERE signal_id=?", [signal_id]).fetchone() == (
        "RECALIBRATION_DUE",
    )
    connection.close()
