import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from etl.config import Settings, read_dotenv
from etl.extract import extract_pages, fetch_with_retry
from etl.pipeline import run
from etl.source import RAW_APPOINTMENTS
from etl.transform import transform

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
        with self.assertLogs("etl.transform", "WARNING"):
            self.assertIsNone(transform({**VALID, "appt_id": None}))

    def test_bad_date_is_skipped(self):
        for date in ("15-04-2024", "2024-13-01", None):
            with self.subTest(date=date), self.assertLogs("etl.transform", "WARNING"):
                self.assertIsNone(transform({**VALID, "date": date}))

    def test_missing_required_field_is_skipped(self):
        for field in ("clinic", "owner", "pet", "time", "status"):
            with self.subTest(field=field), self.assertLogs("etl.transform", "WARNING"):
                self.assertIsNone(transform({**VALID, field: "  "}))

    def test_bad_duration_is_null_but_kept(self):
        for duration in ("sixty", None):
            with (
                self.subTest(duration=duration),
                self.assertLogs("etl.transform", "WARNING"),
            ):
                self.assertIsNone(
                    transform({**VALID, "duration_mins": duration})["duration_mins"]
                )


class ExtractTests(unittest.TestCase):
    def test_reads_all_pages(self):
        for page_size in (1, 2, 3, 4, 10):
            with (
                self.subTest(page_size=page_size),
                self.assertLogs("etl.extract", "INFO"),
            ):
                records = [raw for page in extract_pages(page_size) for raw in page]
                self.assertEqual(records, RAW_APPOINTMENTS)

    @mock.patch("etl.extract.time.sleep")
    def test_retries_with_exponential_backoff(self, sleep):
        fetch = mock.Mock(
            side_effect=[ConnectionError, TimeoutError, {"total": 0, "data": []}]
        )
        with self.assertLogs("etl.extract", "WARNING"):
            fetch_with_retry(1, 3, fetch, max_retries=4, backoff_seconds=0.5)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.5, 1.0])

    @mock.patch("etl.extract.time.sleep")
    def test_gives_up_after_max_retries(self, _):
        fetch = mock.Mock(side_effect=ConnectionError)
        with (
            self.assertLogs("etl.extract", "WARNING"),
            self.assertRaises(ConnectionError),
        ):
            fetch_with_retry(1, 3, fetch, max_retries=3, backoff_seconds=0.5)
        self.assertEqual(fetch.call_count, 3)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(Settings.from_env({}), Settings())

    def test_reads_and_casts_env(self):
        settings = Settings.from_env(
            {"ETL_DB_PATH": "x.db", "ETL_PAGE_SIZE": "10", "ETL_BACKOFF_SECONDS": "0.1"}
        )
        self.assertEqual(
            (settings.db_path, settings.page_size, settings.backoff_seconds),
            ("x.db", 10, 0.1),
        )

    def test_rejects_invalid_values(self):
        for value in ("0", "-1", "three"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Settings.from_env({"ETL_PAGE_SIZE": value})

    def test_read_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('ETL_PAGE_SIZE = 5\nETL_DB_PATH="a.db"\n', encoding="utf-8")
            self.assertEqual(
                read_dotenv(path), {"ETL_PAGE_SIZE": "5", "ETL_DB_PATH": "a.db"}
            )


class PipelineTests(unittest.TestCase):
    def test_end_to_end_and_rerun_has_no_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "test.db")
            with self.assertLogs("etl", "INFO"):
                first = run(Settings(db_path=db))
                second = run(Settings(db_path=db, page_size=4))
            conn = sqlite3.connect(db)
            rows = conn.execute(
                "SELECT appt_id, duration_mins, processed_at FROM appointments ORDER BY 1"
            ).fetchall()
            conn.close()
        self.assertEqual(first, {"extracted": 6, "loaded": 4, "skipped": 2})
        self.assertEqual(second, first)
        self.assertEqual([r[0] for r in rows], ["A001", "A003", "A004", "A005"])
        self.assertIsNone(rows[1][1])
        self.assertTrue(all(r[2] for r in rows))

    def test_records_each_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "test.db")
            with self.assertLogs("etl", "INFO"):
                run(Settings(db_path=db))
                run(Settings(db_path=db, page_size=4))
            conn = sqlite3.connect(db)
            runs = conn.execute(
                "SELECT run_id, status, page_size, extracted, loaded, skipped, finished_at, error "
                "FROM pipeline_runs ORDER BY run_id"
            ).fetchall()
            conn.close()
        self.assertEqual(
            [r[:6] for r in runs],
            [(1, "succeeded", 3, 6, 4, 2), (2, "succeeded", 4, 6, 4, 2)],
        )
        self.assertTrue(all(r[6] and r[7] is None for r in runs))

    @mock.patch("etl.extract.time.sleep")
    def test_failed_run_is_recorded(self, _):
        fetch = mock.Mock(side_effect=ConnectionError("api down"))
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "test.db")
            with self.assertLogs("etl", "INFO"), self.assertRaises(ConnectionError):
                run(Settings(db_path=db, max_retries=2), fetch=fetch)
            conn = sqlite3.connect(db)
            status, error = conn.execute(
                "SELECT status, error FROM pipeline_runs"
            ).fetchone()
            conn.close()
        self.assertEqual(status, "failed")
        self.assertIn("api down", error)


if __name__ == "__main__":
    unittest.main()
