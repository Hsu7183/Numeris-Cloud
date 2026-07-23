from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime

from app.core.paths import BACKUP_DIR, CONFIG_DIR, DATABASE_PATH


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUP_DIR / stamp
    destination.mkdir(parents=True, exist_ok=True)
    if DATABASE_PATH.exists():
        source = sqlite3.connect(DATABASE_PATH)
        target = sqlite3.connect(destination / "numeris.sqlite3")
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
    shutil.make_archive(str(destination / "config"), "zip", CONFIG_DIR)
    backups = sorted(
        [path for path in BACKUP_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    )
    for old in backups[10:]:
        shutil.rmtree(old)
    print(f"備份完成：{destination}")


if __name__ == "__main__":
    main()
