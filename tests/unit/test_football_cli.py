import json

from sports_engine.cli import football
from sports_engine.sports.football.quality.report import CompetitionQualitySummary


class _Connection:
    def close(self) -> None:
        pass


def test_quality_json_is_ascii_safe_for_legacy_windows_console(monkeypatch, capsys) -> None:
    summary = CompetitionQualitySummary(
        competition="Kırmızı League",
        season=2026,
        ledger_mode="production",
        total=1,
        completed=0,
        enriched=0,
        ml_eligible=0,
        pending_repair=0,
        quarantined=0,
        unavailable_components=0,
        completeness_percentage=0.0,
        common_missing=(),
    )
    monkeypatch.setattr(football, "load_config", lambda: object())
    monkeypatch.setattr(football, "open_database", lambda _config: _Connection())
    monkeypatch.setattr(football, "quality_summary", lambda _connection: [summary])

    football.quality(summary=True, detailed=False, as_json=True)

    output = capsys.readouterr().out
    assert "\\u0131" in output
    assert json.loads(output)["summary"][0]["competition"] == "Kırmızı League"
