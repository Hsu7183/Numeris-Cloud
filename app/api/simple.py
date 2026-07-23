from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_models import SimpleGenerationRequest
from app.services.simple_dashboard import create_simple_recommendation, simple_dashboard

router = APIRouter(tags=["簡易選號"])


@router.get("/api/simple/dashboard/{game_code}")
def dashboard(game_code: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return simple_dashboard(db, game_code)


@router.post("/api/simple/generate")
def generate(
    request: SimpleGenerationRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return create_simple_recommendation(db, request)

