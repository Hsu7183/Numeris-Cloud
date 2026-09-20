from __future__ import annotations

from app.models.database_models import ReplayDrawResult, ReplayRun
from app.services.replay.anchor import (
    WALK_FORWARD_ANCHOR_SCOPE,
    calculate_walk_forward_anchor,
    walk_forward_manifest,
)


def _objects() -> tuple[ReplayRun, ReplayDrawResult, dict[str, object]]:
    replay = ReplayRun(
        run_uuid="00000000-0000-0000-0000-000000000001",
        game_id=1,
        preset_id=1,
        start_draw_id=10,
        end_draw_id=20,
        lookback_count=20,
        tickets_per_draw=10,
        seed_policy="per_draw_sha256",
        baseline_repetitions=0,
        config_json={"strategy": "coverage", "random_seed": 123},
        status="completed",
        progress_current=1,
        progress_total=1,
    )
    result = ReplayDrawResult(
        replay_run_id=1,
        target_draw_id=20,
        cutoff_draw_id=19,
        generated_ticket_count=2,
        hit_distribution_json={},
        baseline_distribution_json={},
        result_json={},
    )
    detail: dict[str, object] = {
        "target_draw_no": "D0020",
        "target_draw_date": "2026-07-20",
        "analysis_draw_ids": [1, 2, 3, 19],
        "predicted_tickets": [[1, 2, 3], [4, 5, 6]],
        "actual_numbers": [3, 8, 9],
        "prediction_mode": "coverage",
        "coverage_target_hits": 2,
    }
    return replay, result, detail


def test_walk_forward_anchor_excludes_outcome_and_catches_prediction_change() -> None:
    replay, result, detail = _objects()
    original = calculate_walk_forward_anchor(replay, result, detail)
    detail["actual_numbers"] = [1, 2, 3]
    assert calculate_walk_forward_anchor(replay, result, detail) == original
    detail["predicted_tickets"] = [[1, 2, 4], [4, 5, 6]]
    assert calculate_walk_forward_anchor(replay, result, detail) != original

    manifest = walk_forward_manifest(replay, result, detail)
    assert manifest["scope"] == WALK_FORWARD_ANCHOR_SCOPE
    assert "actual_numbers" not in manifest
