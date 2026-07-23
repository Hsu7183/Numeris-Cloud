from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, update

from app import __version__
from app.api import (
    analytics,
    data_update,
    draws,
    evaluations,
    games,
    generation,
    health,
    replay,
    settings,
)
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import NumerisError
from app.core.logging import configure_logging
from app.core.paths import STATIC_DIR, TEMPLATE_DIR, ensure_directories
from app.models import database_models  # noqa: F401
from app.models.database_models import Draw, Game, Job
from app.services.bootstrap import initialize_catalog

LOGGER = logging.getLogger("application")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_directories()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.execute(
            update(Job)
            .where(Job.status == "running")
            .values(status="interrupted", message="程式重啟，原工作已中斷")
        )
        db.commit()
        initialize_catalog(db)
    LOGGER.info("Numeris %s 啟動完成", __version__)
    yield
    LOGGER.info("Numeris 已關閉")


configure_logging()
app = FastAPI(
    title="Numeris 彩球分析與選號系統",
    version=__version__,
    description="官方歷史開獎資料管理、描述統計及條件式號碼組合",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Any]]):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(NumerisError)
async def numeris_error_handler(request: Request, exc: NumerisError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "detail": exc.detail,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "REQUEST_VALIDATION",
            "message": "請求內容不符合格式或數值範圍",
            "detail": {"errors": exc.errors()},
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("未處理錯誤")
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "系統發生未預期錯誤，詳細資訊已寫入日誌",
            "detail": {},
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


for router in (
    health.router,
    games.router,
    draws.router,
    analytics.router,
    data_update.router,
    generation.router,
    evaluations.router,
    replay.router,
    settings.router,
):
    app.include_router(router)


@app.get("/api/overview")
def overview() -> dict[str, object]:
    with SessionLocal() as db:
        game_rows = list(db.scalars(select(Game).order_by(Game.market_code, Game.id)))
        statuses = []
        for game in game_rows:
            draw_count = int(
                db.scalar(select(func.count()).select_from(Draw).where(Draw.game_id == game.id))
                or 0
            )
            latest = db.scalar(
                select(Draw)
                .where(Draw.game_id == game.id)
                .order_by(Draw.draw_date.desc(), Draw.draw_no.desc())
            )
            conflict_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(Draw)
                    .where(Draw.game_id == game.id, Draw.verification_status == "conflict")
                )
                or 0
            )
            statuses.append(
                {
                    "game_code": game.game_code,
                    "market_code": game.market_code,
                    "display_name": game.display_name_zh_tw,
                    "draw_count": draw_count,
                    "latest_draw_no": latest.draw_no if latest else None,
                    "latest_draw_date": latest.draw_date.isoformat() if latest else None,
                    "verification_status": latest.verification_status if latest else "尚無資料",
                    "conflict_count": conflict_count,
                }
            )
        return {"version": __version__, "games": statuses}


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"app_version": __version__},
    )
