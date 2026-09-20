from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.exceptions import NumerisError
from app.models.database_models import Draw, Game

router = APIRouter(tags=["歷史開獎"])


def _serialize_draw(draw: Draw, game: Game) -> dict[str, object]:
    pools: dict[str, list[int]] = {}
    special: list[int] = []
    for number in draw.numbers:
        if number.is_special:
            special.append(number.number_value)
        else:
            pools.setdefault(number.pool_code, []).append(number.number_value)
    return {
        "game_code": game.game_code,
        "game_name": game.display_name_zh_tw,
        "draw_no": draw.draw_no,
        "draw_date": draw.draw_date.isoformat(),
        "pools": pools,
        "special_numbers": special,
        "source_status": draw.source_status,
        "verification_status": draw.verification_status,
        "ruleset_id": draw.ruleset_id,
    }


@router.get("/api/draws")
def list_draws(
    game_code: str | None = None,
    market_code: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    verification_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(Draw).options(selectinload(Draw.numbers)).join(Game)
    count_query = select(func.count()).select_from(Draw).join(Game)
    conditions = []
    if game_code:
        conditions.append(Game.game_code == game_code)
    if market_code:
        conditions.append(Game.market_code == market_code)
    if date_from:
        conditions.append(Draw.draw_date >= date_from)
    if date_to:
        conditions.append(Draw.draw_date <= date_to)
    if verification_status:
        conditions.append(Draw.verification_status == verification_status)
    query = query.where(*conditions)
    count_query = count_query.where(*conditions)
    total = int(db.scalar(count_query) or 0)
    draws = list(
        db.scalars(
            query.order_by(Draw.draw_date.desc(), Draw.draw_no.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    games = {game.id: game for game in db.scalars(select(Game))}
    return {
        "items": [_serialize_draw(draw, games[draw.game_id]) for draw in draws],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/api/draws/{game_code}/{draw_no}")
def get_draw(game_code: str, draw_no: str, db: Session = Depends(get_db)) -> dict[str, object]:
    game = db.scalar(select(Game).where(Game.game_code == game_code))
    if game is None:
        raise NumerisError("GAME_NOT_FOUND", "找不到指定彩種")
    draw = db.scalar(
        select(Draw)
        .where(Draw.game_id == game.id, Draw.draw_no == draw_no)
        .options(selectinload(Draw.numbers))
    )
    if draw is None:
        raise NumerisError("DRAW_NOT_FOUND", "找不到指定期別")
    return _serialize_draw(draw, game)


@router.get("/api/daily539/recent")
def recent_daily539_draws(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return recent Daily 539 draws with a client-ready frequency summary."""
    game = db.scalar(select(Game).where(Game.game_code == "TW_DAILY539"))
    if game is None:
        raise NumerisError("GAME_NOT_FOUND", "找不到今彩539彩種設定")

    draws = list(
        db.scalars(
            select(Draw)
            .where(Draw.game_id == game.id)
            .options(selectinload(Draw.numbers))
            .order_by(Draw.draw_date.desc(), Draw.draw_no.desc())
            .limit(limit)
        )
    )
    if not draws:
        raise NumerisError("NO_DATA", "目前尚無今彩539開獎資料，請先更新官方資料")

    frequencies: dict[int, dict[str, object]] = {
        value: {"number": value, "count": 0, "appearances": []}
        for value in range(1, 40)
    }
    items: list[dict[str, object]] = []
    for draw_index, draw in enumerate(draws, start=1):
        values = sorted(
            number.number_value
            for number in draw.numbers
            if not number.is_special and number.pool_code == "main"
        )
        items.append(
            {
                "draw_no": draw.draw_no,
                "draw_date": draw.draw_date.isoformat(),
                "numbers": values,
                "source_status": draw.source_status,
            }
        )
        for value in values:
            summary = frequencies[value]
            summary["count"] = int(summary["count"]) + 1
            appearances = summary["appearances"]
            if isinstance(appearances, list):
                appearances.append(
                    {
                        "draw_index": draw_index,
                        "draw_no": draw.draw_no,
                    }
                )

    frequency_items = sorted(
        frequencies.values(),
        key=lambda item: (-int(item["count"]), int(item["number"])),
    )
    latest = items[0]
    return {
        "game_name": game.display_name_zh_tw,
        "requested_limit": limit,
        "draw_count": len(items),
        "latest_draw_no": latest["draw_no"],
        "latest_draw_date": latest["draw_date"],
        "draws": items,
        "frequencies": frequency_items,
    }
