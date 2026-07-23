from __future__ import annotations

import logging
from datetime import datetime

from app.core.paths import LOG_DIR, ensure_directories


def configure_logging() -> None:
    ensure_directories()
    log_path = LOG_DIR / f"numeris_{datetime.now():%Y%m%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
