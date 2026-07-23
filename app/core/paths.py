from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "numeris.sqlite3"
RAW_DIR = DATA_DIR / "raw"
IMPORT_DIR = DATA_DIR / "imports"
FIXTURE_DIR = DATA_DIR / "fixtures"
BACKUP_DIR = DATA_DIR / "backups"
REPORT_DIR = PROJECT_ROOT / "reports"
LOG_DIR = PROJECT_ROOT / "logs"
CONFIG_DIR = PROJECT_ROOT / "config"
TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_DIR = PROJECT_ROOT / "app" / "static"


def ensure_directories() -> None:
    for path in (
        DATABASE_DIR,
        RAW_DIR / "taiwan",
        RAW_DIR / "hong_kong",
        IMPORT_DIR,
        FIXTURE_DIR,
        BACKUP_DIR,
        REPORT_DIR / "build",
        REPORT_DIR / "data_quality",
        REPORT_DIR / "generation",
        REPORT_DIR / "evaluation",
        REPORT_DIR / "replay",
        LOG_DIR,
        PROJECT_ROOT / "data" / "cache",
        PROJECT_ROOT / "data" / "normalized",
    ):
        path.mkdir(parents=True, exist_ok=True)
