import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

REQUIRED_TEXT = {
    "clinic": "clinic_id",
    "owner": "owner_name",
    "pet": "pet_name",
    "time": "appointment_time",
    "status": "status",
}


def transform(raw: dict) -> dict | None:
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
        appointment_date = parsed.date().isoformat()
    except ValueError:
        logger.warning("Skipping %s: unparseable date %r", appt_id, raw.get("date"))
        return None

    missing = [
        field for field in REQUIRED_TEXT if not str(raw.get(field) or "").strip()
    ]
    if missing:
        logger.warning(
            "Skipping %s: missing required fields %s", appt_id, ", ".join(missing)
        )
        return None

    try:
        duration_mins = int(raw.get("duration_mins"))
    except (TypeError, ValueError):
        logger.warning(
            "Record %s: invalid duration_mins %r, storing NULL",
            appt_id,
            raw.get("duration_mins"),
        )
        duration_mins = None

    record = {
        target: str(raw[source]).strip() for source, target in REQUIRED_TEXT.items()
    }
    record["owner_name"] = record["owner_name"].title()
    record["status"] = record["status"].lower()
    return {
        "appt_id": appt_id,
        **record,
        "appointment_date": appointment_date,
        "duration_mins": duration_mins,
    }
