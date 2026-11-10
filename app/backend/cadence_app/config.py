from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    secrets_file: Path
    allowed_origins: tuple[str, ...] = field(default=DEFAULT_ALLOWED_ORIGINS)
    garmin_min_interval_s: float = 1.0
    web_dist: Path = REPO_ROOT / "app" / "web" / "dist"
    share_port: int = 8766
    share_host: str = "0.0.0.0"  # phone share server bind address; CADENCE_SHARE_HOST (e.g. 127.0.0.1 behind a reverse proxy)
    public_url: str | None = None  # HTTPS address a reverse proxy (Caddy) serves the share port on; CADENCE_PUBLIC_URL
    scheduler: bool = False
    sync_every_h: float = 3.0
    push_contact: str = "mailto:cadence@example.com"
    weather: bool = False  # Open-Meteo requests; on for the real service, off in tests unless asked for
    food_data_dir: Path | None = None  # the private food-data submodule (the food library crawl); never in this repo
    reading_feed: bool = False  # Europe PMC requests; on for the real service, off in tests unless asked for
    reading_data_dir: Path | None = None  # the private reading-data folder (reading cards); never in this repo

    @property
    def archive_dir(self) -> Path:
        return self.data_dir / "archive"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "cadence.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("CADENCE_DATA_DIR", REPO_ROOT / "data"))
    secrets_file = Path(
        os.environ.get("CADENCE_SECRETS_FILE", REPO_ROOT / ".secrets" / "garmin.env")
    )
    return Settings(
        data_dir=data_dir,
        secrets_file=secrets_file,
        garmin_min_interval_s=float(os.environ.get("CADENCE_GARMIN_MIN_INTERVAL_S", "1.0")),
        web_dist=Path(os.environ.get("CADENCE_WEB_DIST", REPO_ROOT / "app" / "web" / "dist")),
        share_port=int(os.environ.get("CADENCE_SHARE_PORT", "8766")),
        share_host=os.environ.get("CADENCE_SHARE_HOST", "0.0.0.0"),
        allowed_origins=DEFAULT_ALLOWED_ORIGINS + tuple(o.strip().rstrip("/") for o in os.environ.get("CADENCE_EXTRA_ORIGINS", "").split(",") if o.strip()),
        public_url=(os.environ.get("CADENCE_PUBLIC_URL", "").strip().rstrip("/") or None),
        scheduler=os.environ.get("CADENCE_SCHEDULER", "1") != "0",
        sync_every_h=float(os.environ.get("CADENCE_SYNC_EVERY_HOURS", "3")),
        push_contact=os.environ.get("CADENCE_PUSH_CONTACT", "mailto:cadence@example.com"),
        weather=os.environ.get("CADENCE_WEATHER", "1") != "0",
        food_data_dir=Path(os.environ.get("CADENCE_FOOD_DATA_DIR", REPO_ROOT / "food-data")),
        reading_feed=os.environ.get("CADENCE_READING_FEED", "1") != "0",
        reading_data_dir=Path(os.environ.get("CADENCE_READING_DIR", REPO_ROOT / "reading-data")),
    )
