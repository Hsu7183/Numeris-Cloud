from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_models import GenerationRequest
from app.services.exports.generation_export import export_csv, export_json, export_txt
from app.services.generation.service import (
    create_generation_run,
    list_generation_runs,
    lock_generation_run,
    serialize_generation_run,
)

router = APIRouter(tags=["選號與匯出"])


@router.post("/api/generation/run")
def generate(request: GenerationRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    return create_generation_run(db, request)


@router.get("/api/generation/runs")
def list_runs(limit: int = 50, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return list_generation_runs(db, limit)


@router.get("/api/generation/runs/{run_uuid}")
def get_run(run_uuid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return serialize_generation_run(db, run_uuid)


@router.post("/api/generation/runs/{run_uuid}/lock")
def lock_run(run_uuid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return lock_generation_run(db, run_uuid)


@router.get("/api/exports/generation/{run_uuid}.csv")
def generation_csv(run_uuid: str, db: Session = Depends(get_db)) -> Response:
    return Response(
        export_csv(db, run_uuid),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="numeris_{run_uuid}.csv"'},
    )


@router.get("/api/exports/generation/{run_uuid}.json")
def generation_json(run_uuid: str, db: Session = Depends(get_db)) -> Response:
    return Response(
        export_json(db, run_uuid),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="numeris_{run_uuid}.json"'},
    )


@router.get("/api/exports/generation/{run_uuid}.txt")
def generation_txt(run_uuid: str, db: Session = Depends(get_db)) -> Response:
    return Response(
        export_txt(db, run_uuid),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="numeris_{run_uuid}.txt"'},
    )
