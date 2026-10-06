import logging
import time
from collections.abc import Callable
from contextlib import closing

from etl.config import Settings
from etl.extract import Fetch, extract_pages
from etl.load import connect, finish_run, load, start_run
from etl.source import fetch_appointments
from etl.transform import transform

logger = logging.getLogger(__name__)


def _process(
    settings: Settings,
    fetch: Fetch,
    write: Callable[[list[dict]], int],
    counts: dict[str, int],
) -> None:
    for page in extract_pages(
        settings.page_size,
        fetch,
        settings.max_retries,
        settings.backoff_seconds,
    ):
        records = [record for record in map(transform, page) if record]
        counts["extracted"] += len(page)
        counts["loaded"] += write(records)
        counts["skipped"] += len(page) - len(records)


def run(
    settings: Settings, fetch: Fetch = fetch_appointments, dry_run: bool = False
) -> dict[str, int]:
    counts = {"extracted": 0, "loaded": 0, "skipped": 0}
    if dry_run:
        logger.info(
            "Dry run started (page_size=%d); nothing will be written to %s",
            settings.page_size,
            settings.db_path,
        )
        _process(settings, fetch, len, counts)
        logger.info(
            "Dry run completed: extracted=%d would_load=%d skipped=%d",
            counts["extracted"],
            counts["loaded"],
            counts["skipped"],
        )
        return counts

    with closing(connect(settings.db_path)) as conn:
        run_id = start_run(conn, settings.page_size)
        started = time.monotonic()
        logger.info(
            "Pipeline run %d started (db=%s, page_size=%d)",
            run_id,
            settings.db_path,
            settings.page_size,
        )
        try:
            _process(settings, fetch, lambda records: load(conn, records), counts)
        except Exception as exc:
            finish_run(
                conn, run_id, "failed", counts, time.monotonic() - started, repr(exc)
            )
            raise
        finish_run(conn, run_id, "succeeded", counts, time.monotonic() - started)
    logger.info(
        "Pipeline run %d completed: extracted=%d loaded=%d skipped=%d",
        run_id,
        counts["extracted"],
        counts["loaded"],
        counts["skipped"],
    )
    return counts
