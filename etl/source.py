import time

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
