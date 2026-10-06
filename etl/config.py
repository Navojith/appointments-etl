from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path


def _positive(
    env: Mapping[str, str], name: str, cast: Callable[[str], float], default: float
):
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        value = None
    if value is None or value <= 0:
        raise ValueError(f"{name} expected a positive number, got {raw!r}")
    return value


def read_dotenv(path: str | Path = ".env") -> dict[str, str]:
    path = Path(path)
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            values[key.strip()] = value.strip().strip("\"'")
    return values


@dataclass(frozen=True)
class Settings:
    db_path: str = "appointments.db"
    page_size: int = 3
    max_retries: int = 4
    backoff_seconds: float = 0.5
    log_dir: str = "logs"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        d = cls()
        return cls(
            db_path=env.get("ETL_DB_PATH", "").strip() or d.db_path,
            page_size=_positive(env, "ETL_PAGE_SIZE", int, d.page_size),
            max_retries=_positive(env, "ETL_MAX_RETRIES", int, d.max_retries),
            backoff_seconds=_positive(
                env, "ETL_BACKOFF_SECONDS", float, d.backoff_seconds
            ),
            log_dir=env.get("ETL_LOG_DIR", "").strip() or d.log_dir,
        )
