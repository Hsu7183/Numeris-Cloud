from __future__ import annotations

from typing import Any

from app.models.database_models import ReplayDrawResult, ReplayRun
from app.services.bootstrap import canonical_hash

WALK_FORWARD_ANCHOR_VERSION = "NUMERIS_WALK_FORWARD_V1"
WALK_FORWARD_ANCHOR_SCOPE = "RETROSPECTIVE_WALK_FORWARD"


def walk_forward_manifest(
    replay: ReplayRun,
    result: ReplayDrawResult,
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Build evidence from inputs and predictions only; outcomes are excluded."""
    return {
        "anchor_version": WALK_FORWARD_ANCHOR_VERSION,
        "scope": WALK_FORWARD_ANCHOR_SCOPE,
        "replay_run_uuid": replay.run_uuid,
        "target_draw_id": result.target_draw_id,
        "target_draw_no": detail.get("target_draw_no"),
        "target_draw_date": detail.get("target_draw_date"),
        "cutoff_draw_id": result.cutoff_draw_id,
        "analysis_draw_ids": detail.get("analysis_draw_ids", []),
        "generated_ticket_count": result.generated_ticket_count,
        "predicted_tickets": detail.get("predicted_tickets", []),
        "prediction_mode": detail.get("prediction_mode"),
        "coverage_target_hits": detail.get("coverage_target_hits"),
        "tickets_per_draw": replay.tickets_per_draw,
        "lookback_count": replay.lookback_count,
        "seed_policy": replay.seed_policy,
        "replay_config": dict(replay.config_json or {}),
    }


def calculate_walk_forward_anchor(
    replay: ReplayRun,
    result: ReplayDrawResult,
    detail: dict[str, Any],
) -> str:
    return canonical_hash(walk_forward_manifest(replay, result, detail))
