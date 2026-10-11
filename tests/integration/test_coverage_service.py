from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.sports.football.ingestion.coverage_gate import CoverageAuditService, SeasonCatalogService
from sports_engine.warehouse import checkpoints
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def league_payload(provider_id: int, *, players: bool = True) -> dict[str, Any]:
    return {
        "league": {
            "id": provider_id,
            "name": f"League {provider_id}",
            "country": "Country",
            "type": "League",
        },
        "seasons": [
            {
                "year": 2026,
                "start": "2026-01-01",
                "end": "2026-12-31",
                "current": True,
                "coverage": {
                    "fixtures": {
                        "events": True,
                        "lineups": True,
                        "statistics_fixtures": True,
                        "statistics_players": players,
                    },
                    "odds": True,
                },
            }
        ],
    }


def replay_payload(provider_id: int) -> dict[str, Any]:
    payload = league_payload(provider_id)
    payload["seasons"][0]["year"] = 2024
    payload["seasons"][0]["current"] = False
    payload["seasons"][0]["coverage"]["odds"] = False
    return payload


class CoverageProvider:
    def __init__(self, stop_on: int | None = None) -> None:
        self.stop_on = stop_on
        self.requested: list[int] = []

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        provider_id = int(parameters["id"])
        self.requested.append(provider_id)
        if provider_id == self.stop_on:
            raise QuotaExhaustedError("reserve")
        return [league_payload(provider_id, players=provider_id != 2)]


CANDIDATES = [
    {"provider_id": 1, "name": "One", "priority": 1},
    {"provider_id": 2, "name": "Two", "priority": 2},
]


def test_coverage_audit_persists_acceptance_and_rejection(tmp_path: Path) -> None:
    connection = connect(tmp_path / "coverage.duckdb")
    migrate(connection)
    result = CoverageAuditService(
        connection,
        CoverageProvider(),
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run(CANDIDATES)
    assert result.complete
    assert [item.accepted for item in result.items] == [True, False]
    assert connection.execute("SELECT admitted FROM competition_seasons ORDER BY priority").fetchall() == [
        (True,),
        (False,),
    ]
    assert checkpoints.get(connection, CoverageAuditService.checkpoint_key) == 0
    connection.close()


def test_coverage_audit_resumes_after_quota_stop(tmp_path: Path) -> None:
    connection = connect(tmp_path / "coverage.duckdb")
    migrate(connection)
    stopped_provider = CoverageProvider(stop_on=2)
    service = CoverageAuditService(
        connection,
        stopped_provider,
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    )
    first = service.run(CANDIDATES)
    assert not first.complete and first.next_candidate_index == 1
    resumed_provider = CoverageProvider()
    second = CoverageAuditService(
        connection,
        resumed_provider,
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run(CANDIDATES)
    assert second.complete
    assert resumed_provider.requested == [2]
    assert connection.execute("SELECT count(*) FROM competition_seasons").fetchone() == (2,)
    connection.close()


def test_replay_audit_requests_exact_year_and_labels_ledger(tmp_path: Path) -> None:
    connection = connect(tmp_path / "replay.duckdb")
    migrate(connection)

    class ReplayProvider(CoverageProvider):
        def get(self, endpoint: str, parameters: Mapping[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
            assert parameters == {"id": 1, "season": 2024}
            return [replay_payload(1)]

    result = CoverageAuditService(
        connection,
        ReplayProvider(),
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run([CANDIDATES[0]], ledger_mode="replay", replay_season=2024)
    assert result.complete and result.items[0].season == 2024
    assert result.items[0].replay_eligible
    assert connection.execute(
        "SELECT provider_season, ledger_mode, admitted, replay_eligible FROM competition_seasons"
    ).fetchone() == (2024, "replay", False, True)
    connection.close()


def test_catalog_registers_five_completed_seasons_per_selected_league_in_one_request(tmp_path: Path) -> None:
    connection = connect(tmp_path / "five-seasons.duckdb")
    migrate(connection)

    class CatalogProvider:
        calls = 0

        def get(self, endpoint: str, parameters: Mapping[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
            self.calls += 1
            assert parameters == {"current": "false"}
            rows = []
            for provider_id in (1, 2):
                payload = league_payload(provider_id)
                payload["seasons"] = [
                    {
                        **payload["seasons"][0],
                        "year": year,
                        "current": year == 2026,
                    }
                    for year in range(2020, 2027)
                ]
                rows.append(payload)
            return rows

    provider = CatalogProvider()
    result = SeasonCatalogService(
        connection,
        provider,
        raw_path_resolver=lambda purpose, run_id: "catalog.json.gz",
    ).run(CANDIDATES, past_seasons=5)
    assert provider.calls == 1
    assert result.provider_seasons == (2025, 2024, 2023, 2022, 2021)
    assert result.competition_seasons_registered == 10
    assert len(result.items) == 10
    assert connection.execute(
        "SELECT count(*) FROM competition_seasons WHERE ledger_mode='replay' AND replay_eligible"
    ).fetchone() == (10,)
    connection.close()
