from sports_engine.providers.api_football.coverage import assess_coverage


def test_coverage_gate_requires_all_mandatory_capabilities() -> None:
    payload = {
        "fixtures": {
            "events": True,
            "lineups": True,
            "statistics_fixtures": True,
            "statistics_players": False,
        },
        "odds": True,
    }
    result = assess_coverage(payload)
    assert not result.accepted
    assert result.reasons == ("fixtures.statistics_players=false",)
