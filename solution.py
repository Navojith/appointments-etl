import argparse
import logging
import math
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

RAW_APPOINTMENTS = [
    {
        "appt_id": "A001",
        "clinic": "paws_clinic",
        "owner": "john doe",
        "pet": "buddy",
        "date": "2024-04-15",
        "time": "09:00",
        "status": "completed",
        "duration_mins": "30",
    },
    {
        "appt_id": "A002",
        "clinic": "happy_vets",
        "owner": "  Jane Smith ",
        "pet": "whiskers",
        "date": "15-04-2024",
        "time": "10:30",
        "status": "NO_SHOW",
        "duration_mins": "45",
    },
    {
        "appt_id": "A003",
        "clinic": "paws_clinic",
        "owner": "alice brown",
        "pet": "rex",
        "date": "2024-04-15",
        "time": "14:00",
        "status": "scheduled",
        "duration_mins": "sixty",
    },
    {
        "appt_id": "A004",
        "clinic": "city_animal_care",
        "owner": "bob jones",
        "pet": "luna",
        "date": "2024-04-16",
        "time": "09:30",
        "status": "completed",
        "duration_mins": "20",
    },
    {
        "appt_id": None,
        "clinic": "happy_vets",
        "owner": "carol white",
        "pet": "milo",
        "date": "2024-04-16",
        "time": "11:00",
        "status": "completed",
        "duration_mins": "30",
    },
    {
        "appt_id": "A005",
        "clinic": "paws_clinic",
        "owner": "dave miller",
        "pet": "bella",
        "date": "2024-04-16",
        "time": "13:00",
        "status": "cancelled",
        "duration_mins": "30",
    },
]


def fetch_appointments(page: int = 1, page_size: int = 3) -> dict:
    """Simulated paginated API with realistic latency."""
    time.sleep(0.05)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "page": page,
        "page_size": page_size,
        "total": len(RAW_APPOINTMENTS),
        "data": RAW_APPOINTMENTS[start:end],
    }


logger = logging.getLogger("appointments_etl")

SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    appt_id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    pet_name TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_mins INTEGER,
    processed_at TEXT NOT NULL
)
"""

UPSERT = """
INSERT INTO appointments VALUES (
    :appt_id, :clinic_id, :owner_name, :pet_name, :appointment_date,
    :appointment_time, :status, :duration_mins, :processed_at
)
ON CONFLICT (appt_id) DO UPDATE SET
    clinic_id = excluded.clinic_id,
    owner_name = excluded.owner_name,
    pet_name = excluded.pet_name,
    appointment_date = excluded.appointment_date,
    appointment_time = excluded.appointment_time,
    status = excluded.status,
    duration_mins = excluded.duration_mins,
    processed_at = excluded.processed_at
"""


def fetch_with_retry(
    page, page_size, fetch=fetch_appointments, attempts=4, base_delay=0.5
):
    for attempt in range(1, attempts + 1):
        try:
            return fetch(page, page_size)
        except (ConnectionError, TimeoutError) as exc:
            if attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            logger.warning(
                "Page %d failed (attempt %d/%d): %s. Retrying in %.1fs",
                page,
                attempt,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)


def extract(page_size, fetch=fetch_appointments):
    first = fetch_with_retry(1, page_size, fetch)
    pages = math.ceil(first["total"] / page_size)
    yield from first["data"]
    for page in range(2, pages + 1):
        yield from fetch_with_retry(page, page_size, fetch)["data"]


def transform(raw):
    appt_id = raw.get("appt_id")
    if not appt_id:
        logger.warning(
            "Skipping record: missing appt_id (clinic=%s, date=%s)",
            raw.get("clinic"),
            raw.get("date"),
        )
        return None

    try:
        parsed = datetime.strptime(str(raw.get("date")), "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        date = parsed.date().isoformat()
    except ValueError:
        logger.warning("Skipping %s: unparseable date %r", appt_id, raw.get("date"))
        return None

    try:
        duration = int(raw.get("duration_mins"))
    except (TypeError, ValueError):
        logger.warning(
            "Record %s: invalid duration_mins %r, storing NULL",
            appt_id,
            raw.get("duration_mins"),
        )
        duration = None

    return {
        "appt_id": appt_id,
        "clinic_id": raw["clinic"],
        "owner_name": raw["owner"].strip().title(),
        "pet_name": raw["pet"],
        "appointment_date": date,
        "appointment_time": raw["time"],
        "status": raw["status"].lower(),
        "duration_mins": duration,
    }


def load(conn, records):
    processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.executemany(
            UPSERT, [{**record, "processed_at": processed_at} for record in records]
        )
    return len(records)


def run(db_path="appointments.db", page_size=3, fetch=fetch_appointments):
    logger.info("Pipeline started (db=%s, page_size=%d)", db_path, page_size)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        extracted = 0
        valid = []
        for raw in extract(page_size, fetch):
            extracted += 1
            record = transform(raw)
            if record:
                valid.append(record)
        loaded = load(conn, valid)
    finally:
        conn.close()
    logger.info(
        "Pipeline completed: extracted=%d loaded=%d skipped=%d",
        extracted,
        loaded,
        extracted - loaded,
    )
    return extracted, loaded


def main():
    parser = argparse.ArgumentParser(
        description="Load clinic appointments into SQLite."
    )
    parser.add_argument("--page-size", type=int, default=3)
    parser.add_argument("--db-path", default="appointments.db")
    parser.add_argument(
        "--test", action="store_true", help="run the unit tests and exit"
    )
    args = parser.parse_args()
    if args.test:
        unittest.main(argv=[sys.argv[0], "-v"])
    if args.page_size < 1:
        parser.error("--page-size must be at least 1")

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    run(args.db_path, args.page_size)


VALID = {
    "appt_id": "A100",
    "clinic": "paws_clinic",
    "owner": "  jane SMITH ",
    "pet": "rex",
    "date": "2024-04-15",
    "time": "09:00",
    "status": "NO_SHOW",
    "duration_mins": "30",
}


class TransformTests(unittest.TestCase):
    def test_valid_record(self):
        self.assertEqual(
            transform(VALID),
            {
                "appt_id": "A100",
                "clinic_id": "paws_clinic",
                "owner_name": "Jane Smith",
                "pet_name": "rex",
                "appointment_date": "2024-04-15",
                "appointment_time": "09:00",
                "status": "no_show",
                "duration_mins": 30,
            },
        )

    def test_missing_appt_id_is_skipped(self):
        with self.assertLogs(logger, "WARNING"):
            self.assertIsNone(transform({**VALID, "appt_id": None}))

    def test_bad_date_is_skipped(self):
        for date in ("15-04-2024", "2024-13-01", None):
            with self.subTest(date=date), self.assertLogs(logger, "WARNING"):
                self.assertIsNone(transform({**VALID, "date": date}))

    def test_bad_duration_is_null_but_kept(self):
        for duration in ("sixty", None):
            with self.subTest(duration=duration), self.assertLogs(logger, "WARNING"):
                self.assertIsNone(
                    transform({**VALID, "duration_mins": duration})["duration_mins"]
                )


class ExtractTests(unittest.TestCase):
    def test_reads_all_pages(self):
        for page_size in (1, 2, 3, 4, 10):
            with self.subTest(page_size=page_size):
                self.assertEqual(list(extract(page_size)), RAW_APPOINTMENTS)

    @mock.patch.object(time, "sleep")
    def test_retries_with_backoff(self, sleep):
        fetch = mock.Mock(
            side_effect=[ConnectionError, ConnectionError, {"total": 0, "data": []}]
        )
        with self.assertLogs(logger, "WARNING"):
            fetch_with_retry(1, 3, fetch)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.5, 1.0])

    @mock.patch.object(time, "sleep")
    def test_gives_up_after_max_attempts(self, _):
        fetch = mock.Mock(side_effect=ConnectionError)
        with self.assertLogs(logger, "WARNING"), self.assertRaises(ConnectionError):
            fetch_with_retry(1, 3, fetch, attempts=3)
        self.assertEqual(fetch.call_count, 3)


class RunTests(unittest.TestCase):
    def test_end_to_end_and_rerun_has_no_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "test.db")
            with self.assertLogs(logger, "INFO"):
                self.assertEqual(run(db), (6, 4))
                self.assertEqual(run(db, page_size=4), (6, 4))
            conn = sqlite3.connect(db)
            rows = conn.execute(
                "SELECT appt_id, duration_mins, processed_at FROM appointments ORDER BY 1"
            ).fetchall()
            conn.close()
        self.assertEqual([r[0] for r in rows], ["A001", "A003", "A004", "A005"])
        self.assertIsNone(rows[1][1])
        self.assertTrue(all(r[2] for r in rows))


if __name__ == "__main__":
    main()
