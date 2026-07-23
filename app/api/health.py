from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.database import database_status

router = APIRouter(tags=["系統健康"])


@router.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "Numeris 彩球分析與選號系統",
        "version": __version__,
        "database": database_status(),
        "timezone": "Asia/Taipei",
    }
