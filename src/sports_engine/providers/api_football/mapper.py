from typing import Any


def statistic_map(statistics: list[dict[str, Any]]) -> dict[str, Any]:
    return {str(item.get("type")): item.get("value") for item in statistics}
