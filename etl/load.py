import sqlite3
from datetime import datetime, timezone

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
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    page_size INTEGER NOT NULL,
    extracted INTEGER NOT NULL DEFAULT 0,
    loaded INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL,
    error TEXT
);
"""

UPSERT = """
INSERT INTO appointments (
    appt_id, clinic_id, owner_name, pet_name, appointment_date,
    appointment_time, status, duration_mins, processed_at
) VALUES (
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


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(conn: sqlite3.Connection, records: list[dict]) -> int:
    if not records:
        return 0
    processed_at = _now()
    with conn:
        conn.executemany(
            UPSERT, [{**record, "processed_at": processed_at} for record in records]
        )
    return len(records)


def start_run(conn: sqlite3.Connection, page_size: int) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO pipeline_runs (started_at, status, page_size) VALUES (?, 'running', ?)",
            (_now(), page_size),
        )
    return cursor.lastrowid


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    counts: dict[str, int],
    duration_seconds: float,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = :finished_at, status = :status, extracted = :extracted, loaded = :loaded,
                skipped = :skipped, duration_seconds = :duration_seconds, error = :error
            WHERE run_id = :run_id
            """,
            {
                **counts,
                "run_id": run_id,
                "finished_at": _now(),
                "status": status,
                "duration_seconds": round(duration_seconds, 3),
                "error": error,
            },
        )
