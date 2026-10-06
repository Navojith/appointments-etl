import logging
import math
import time
from collections.abc import Callable, Iterator

from etl.source import fetch_appointments

logger = logging.getLogger(__name__)

Fetch = Callable[[int, int], dict]


def fetch_with_retry(
    page: int, page_size: int, fetch: Fetch, max_retries: int, backoff_seconds: float
) -> dict:
    for attempt in range(1, max_retries + 1):
        try:
            return fetch(page, page_size)
        except (ConnectionError, TimeoutError) as exc:
            if attempt == max_retries:
                raise
            delay = backoff_seconds * 2 ** (attempt - 1)
            logger.warning(
                "Page %d failed (attempt %d/%d): %s. Retrying in %.1fs",
                page,
                attempt,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)
    raise ValueError("max_retries must be at least 1")


def extract_pages(
    page_size: int,
    fetch: Fetch = fetch_appointments,
    max_retries: int = 4,
    backoff_seconds: float = 0.5,
) -> Iterator[list[dict]]:
    first = fetch_with_retry(1, page_size, fetch, max_retries, backoff_seconds)
    total_pages = math.ceil(first["total"] / page_size)
    logger.info("Source has %d records across %d pages", first["total"], total_pages)
    yield first["data"]
    for page in range(2, total_pages + 1):
        yield fetch_with_retry(page, page_size, fetch, max_retries, backoff_seconds)[
            "data"
        ]
