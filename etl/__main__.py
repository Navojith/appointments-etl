import argparse
import logging
import os
import sys
from dataclasses import replace
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from etl.config import Settings, read_dotenv
from etl.pipeline import run

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        Path(log_dir) / "etl.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    logging.basicConfig(
        level=os.environ.get("ETL_LOG_LEVEL", "INFO").upper(),
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler(), file_handler],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl", description="Load clinic appointments into SQLite."
    )
    parser.add_argument(
        "--page-size", type=int, help="records per API page (overrides ETL_PAGE_SIZE)"
    )
    parser.add_argument(
        "--db-path", help="SQLite database path (overrides ETL_DB_PATH)"
    )
    args = parser.parse_args()

    try:
        settings = Settings.from_env({**read_dotenv(), **os.environ})
    except ValueError as exc:
        parser.error(str(exc))
    if args.page_size is not None and args.page_size < 1:
        parser.error("--page-size must be at least 1")
    overrides = {"page_size": args.page_size, "db_path": args.db_path}
    settings = replace(
        settings,
        **{key: value for key, value in overrides.items() if value is not None},
    )
    configure_logging(settings.log_dir)

    try:
        run(settings)
    except Exception:
        logging.getLogger("etl").exception("Pipeline failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
