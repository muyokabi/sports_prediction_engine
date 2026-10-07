import random


def backoff_seconds(attempt: int, base: float, *, jitter: float = 0.25) -> float:
    delay = base * (2**attempt)
    return delay + random.uniform(0.0, delay * jitter)
