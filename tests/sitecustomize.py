"""測試程序在應用程式匯入前隔離資料庫並載入NumPy。

Windows應用程式控制搭配Python 3.13的trace hook會阻止NumPy原生模組於
追蹤啟動後首次載入；預先載入不影響正式應用程式。
"""

import os
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
test_db = project_root / "data" / "cache" / f"numeris_pytest_{os.getpid()}.sqlite3"
if "NUMERIS_DATABASE_URL" not in os.environ:
    test_db.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        test_db.with_name(test_db.name + suffix).unlink(missing_ok=True)
    os.environ["NUMERIS_DATABASE_URL"] = f"sqlite:///{test_db.as_posix()}"

import numpy  # noqa: E402, F401
