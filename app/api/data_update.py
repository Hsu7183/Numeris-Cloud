from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NumerisError
from app.core.paths import IMPORT_DIR
from app.models.database_models import Job
from app.services.data_sources.official import (
    create_update_job,
    job_to_dict,
    run_update_job,
)
from app.services.importers.draw_importer import import_file, summary_dict

router = APIRouter(tags=["資料中心與工作"])


@router.post("/api/data/update")
def update_data(
    background_tasks: BackgroundTasks,
    scope: str = "all",
    db: Session = Depends(get_db),
) -> dict[str, str]:
    result = create_update_job(db, scope)
    background_tasks.add_task(run_update_job, result["job_uuid"])
    return result


@router.get("/api/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    jobs = list(db.scalars(select(Job).order_by(Job.id.desc()).limit(100)))
    return [job_to_dict(job) for job in jobs]


@router.get("/api/jobs/{job_uuid}")
def get_job(job_uuid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    job = db.scalar(select(Job).where(Job.job_uuid == job_uuid))
    if job is None:
        raise NumerisError("JOB_NOT_FOUND", "找不到系統工作")
    return job_to_dict(job)


@router.post("/api/jobs/{job_uuid}/cancel")
def cancel_job(job_uuid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    job = db.scalar(select(Job).where(Job.job_uuid == job_uuid))
    if job is None:
        raise NumerisError("JOB_NOT_FOUND", "找不到系統工作")
    if job.status in {"pending", "running"}:
        job.status = "cancelled"
        job.message = "使用者已取消工作"
        db.commit()
    return job_to_dict(job)


@router.post("/api/imports/upload")
async def upload_import(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise NumerisError("IMPORT_FORMAT", "僅支援CSV、XLSX與XLS檔案")
    safe_name = Path(file.filename or f"import{suffix}").name
    destination = IMPORT_DIR / safe_name
    destination.write_bytes(await file.read())
    summary = import_file(db, destination)
    return {"filename": safe_name, "summary": summary_dict(summary)}
