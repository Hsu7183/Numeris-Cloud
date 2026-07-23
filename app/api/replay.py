from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_models import ReplayRequest
from app.services.replay.service import create_replay_job, get_replay, run_replay_job

router = APIRouter(tags=["歷史逐期模擬"])


@router.post("/api/replay/run")
def start_replay(
    request: ReplayRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    result = create_replay_job(db, request)
    background_tasks.add_task(run_replay_job, str(result["run_uuid"]))
    return result


@router.get("/api/replay/{run_uuid}")
def replay_status(run_uuid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return get_replay(db, run_uuid)
