from sports_engine.providers.api_football.pagination import pages
from sports_engine.providers.api_football.schemas import ApiEnvelope


def test_pagination_follows_reported_total() -> None:
    seen: list[int] = []

    def fetch(parameters: dict[str, object]) -> ApiEnvelope:
        page = int(parameters["page"])
        seen.append(page)
        return ApiEnvelope.model_validate(
            {
                "get": "odds",
                "parameters": {},
                "errors": [],
                "results": 1,
                "paging": {"current": page, "total": 3},
                "response": [{"page": page}],
            }
        )

    result = list(pages(fetch, {}))
    assert seen == [1, 2, 3]
    assert [item.response[0]["page"] for item in result] == [1, 2, 3]
