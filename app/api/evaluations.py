from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.evaluation.service import evaluate_generation_run, get_evaluation

router = APIRouter(tags=["開獎核對"])


@router.post("/api/generation/runs/{run_uuid}/evaluate")
def evaluate(
    run_uuid: str, actual_draw_no: str | None = None, db: Session = Depends(get_db)
) -> dict[str, object]:
    return evaluate_generation_run(db, run_uuid, actual_draw_no)


@router.get("/api/evaluations/{run_uuid}")
def evaluation(run_uuid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return get_evaluation(db, run_uuid)
