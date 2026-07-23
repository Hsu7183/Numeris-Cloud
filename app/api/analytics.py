from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.analytics.core import calculate_structure
from app.services.generation.service import (
    _draws_for_game,
    _pool_draws,
    analysis_for_game,
    get_game_and_ruleset,
)

router = APIRouter(tags=["分析"])


@router.get("/api/analytics/frequency")
def frequency(
    game_code: str = "TW_LOTTO649",
    lookback_count: int = Query(default=20, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return analysis_for_game(db, game_code, lookback_count)


@router.get("/api/analytics/omission")
def omission(
    game_code: str = "TW_LOTTO649",
    lookback_count: int = Query(default=20, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = analysis_for_game(db, game_code, lookback_count)
    for pool in payload["pools"].values():
        pool["metrics"] = sorted(
            pool["metrics"],
            key=lambda metric: (-metric["current_omission"], metric["number"]),
        )
    return payload


def _structure_payload(db: Session, game_code: str, lookback_count: int) -> dict[str, Any]:
    game, ruleset = get_game_and_ruleset(db, game_code)
    draws = _draws_for_game(db, game)[-lookback_count:]
    pool = ruleset.config_json["pools"][0]
    samples, draw_nos = _pool_draws(draws, str(pool["code"]))
    structures = [
        calculate_structure(
            numbers,
            int(pool["high_boundary"]),
            pool["zones"],
            samples[index - 1] if index > 0 else None,
            include_ac=game.supports_ac,
        )
        for index, numbers in enumerate(samples)
    ]
    distributions = {
        key: dict(sorted(Counter(item[key] for item in structures).items()))
        for key in ("odd_count", "high_count", "sum", "span", "consecutive_pairs")
    }
    if game.supports_ac:
        distributions["ac"] = dict(sorted(Counter(item["ac"] for item in structures).items()))
    return {
        "game_code": game_code,
        "lookback_count": len(structures),
        "draw_nos": draw_nos,
        "distributions": distributions,
        "items": structures,
    }


@router.get("/api/analytics/structure")
def structure(
    game_code: str = "TW_LOTTO649",
    lookback_count: int = Query(default=100, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _structure_payload(db, game_code, lookback_count)


@router.get("/api/analytics/ac")
def ac(
    game_code: str = "TW_LOTTO649",
    lookback_count: int = Query(default=100, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = _structure_payload(db, game_code, lookback_count)
    values = [item["ac"] for item in payload["items"] if item["ac"] is not None]
    payload["applicable"] = bool(values)
    payload["message"] = "本遊戲不適用AC值，請使用數字結構篩選。" if not values else "AC值分布"
    return payload
