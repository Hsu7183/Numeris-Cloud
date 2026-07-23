from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NumerisError
from app.models.database_models import Draw, Game, Ruleset

router = APIRouter(tags=["彩種與規則"])


def _game_payload(db: Session, game: Game) -> dict[str, object]:
    ruleset = db.scalar(
        select(Ruleset).where(Ruleset.game_id == game.id).order_by(Ruleset.id.desc())
    )
    draw_count = db.scalar(select(func.count()).select_from(Draw).where(Draw.game_id == game.id))
    latest = db.scalar(
        select(Draw)
        .where(Draw.game_id == game.id)
        .order_by(Draw.draw_date.desc(), Draw.draw_no.desc())
    )
    return {
        "game_code": game.game_code,
        "market_code": game.market_code,
        "display_name": game.display_name_zh_tw,
        "display_name_en": game.display_name_en,
        "game_type": game.game_type,
        "parent_game_code": game.parent_game_code,
        "supports_ac": game.supports_ac,
        "supports_special_ball": game.supports_special_ball,
        "supports_multiple_pools": game.supports_multiple_pools,
        "active": game.active,
        "draw_count": draw_count or 0,
        "latest_draw_no": latest.draw_no if latest else None,
        "latest_draw_date": latest.draw_date.isoformat() if latest else None,
        "ruleset": {
            "version": ruleset.version,
            "verified": ruleset.verified,
            "status": ruleset.status,
            "source_reference": ruleset.source_reference,
            "config": ruleset.config_json,
        }
        if ruleset
        else None,
    }


@router.get("/api/games")
def list_games(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    games = list(db.scalars(select(Game).order_by(Game.market_code, Game.id)))
    return [_game_payload(db, game) for game in games]


@router.get("/api/games/{game_code}")
def get_game(game_code: str, db: Session = Depends(get_db)) -> dict[str, object]:
    game = db.scalar(select(Game).where(Game.game_code == game_code))
    if game is None:
        raise NumerisError("GAME_NOT_FOUND", "找不到指定彩種", {"game_code": game_code})
    return _game_payload(db, game)
