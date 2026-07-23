from __future__ import annotations

from pathlib import Path

from app.core.paths import PROJECT_ROOT


def safe_project_path(path: Path) -> Path:
    resolved = path.resolve()
    if PROJECT_ROOT.resolve() not in resolved.parents and resolved != PROJECT_ROOT.resolve():
        raise ValueError("檔案路徑超出 Numeris 專案範圍")
    return resolved
