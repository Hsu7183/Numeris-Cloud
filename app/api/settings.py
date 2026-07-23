from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database_models import AppSetting

router = APIRouter(tags=["系統設定"])


class SettingsPayload(BaseModel):
    value: dict[str, Any]


@router.get("/api/settings")
def list_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {row.key: row.value_json for row in db.scalars(select(AppSetting))}


@router.put("/api/settings/{key}")
def update_setting(
    key: str, payload: SettingsPayload, db: Session = Depends(get_db)
) -> dict[str, Any]:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value_json=payload.value)
        db.add(row)
    else:
        row.value_json = payload.value
    db.commit()
    return {"key": key, "value": row.value_json}
