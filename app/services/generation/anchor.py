from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.database_models import Draw, Game, GenerationPreset, GenerationRun
from app.services.bootstrap import canonical_hash

RECOMMENDATION_ANCHOR_VERSION = "NUMERIS_RECOMMENDATION_V1"
ANCHOR_CONFIG_KEYS = {
    "anchor_version",
    "recommendation_anchor",
    "anchor_locked_at",
    "anchor_cutoff_draw_id",
}


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def recommendation_manifest(
    db: Session,
    run: GenerationRun,
) -> dict[str, Any]:
    game = db.get(Game, run.game_id)
    cutoff = db.get(Draw, run.cutoff_draw_id)
    preset = db.get(GenerationPreset, run.preset_id)
    locked_at = as_utc(run.locked_at)
    stable_config = {
        key: value
        for key, value in dict(run.config_json or {}).items()
        if key not in ANCHOR_CONFIG_KEYS
    }
    tickets: list[dict[str, Any]] = []
    for ticket in sorted(run.tickets, key=lambda item: (item.ticket_index, item.id)):
        numbers = sorted(
            ticket.numbers,
            key=lambda item: (
                item.pool_code,
                item.display_order if item.display_order is not None else 999,
                item.position_index if item.position_index is not None else 999,
                item.id,
            ),
        )
        tickets.append(
            {
                "ticket_index": ticket.ticket_index,
                "ticket_hash": ticket.ticket_hash,
                "numbers": [
                    {
                        "pool_code": number.pool_code,
                        "position_index": number.position_index,
                        "display_order": number.display_order,
                        "number_value": number.number_value,
                    }
                    for number in numbers
                ],
            }
        )
    return {
        "anchor_version": RECOMMENDATION_ANCHOR_VERSION,
        "game_code": game.game_code if game else None,
        "target_draw_no": run.target_draw_no,
        "cutoff_draw_id": run.cutoff_draw_id,
        "cutoff_draw_no": cutoff.draw_no if cutoff else None,
        "preset_code": preset.preset_code if preset else None,
        "random_seed": run.random_seed,
        "locked_at": locked_at.isoformat() if locked_at else None,
        "config": stable_config,
        "tickets": tickets,
    }


def calculate_recommendation_anchor(
    db: Session,
    run: GenerationRun,
) -> str:
    return canonical_hash(recommendation_manifest(db, run))


def verify_recommendation_anchor(
    db: Session,
    run: GenerationRun,
) -> bool:
    config = dict(run.config_json or {})
    stored = config.get("recommendation_anchor")
    if (
        not run.locked
        or run.locked_at is None
        or not isinstance(stored, str)
        or config.get("anchor_version") != RECOMMENDATION_ANCHOR_VERSION
    ):
        return False
    calculated = calculate_recommendation_anchor(db, run)
    return hmac.compare_digest(stored, calculated)


def draw_arrived_after_lock(run: GenerationRun, draw: Draw) -> bool:
    locked_at = as_utc(run.locked_at)
    created_at = as_utc(draw.created_at)
    return bool(locked_at and created_at and created_at > locked_at)
