from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.paths import REPORT_DIR
from app.models.api_models import ReplayRequest
from app.models.database_models import Draw, Game, GenerationPreset, ReplayRun
from app.services.replay.service import (
    create_replay_job,
    get_replay,
    run_replay_job,
)

GAME_CODES = (
    "HK_MARKSIX",
    "TW_39MATCH",
    "TW_49MATCH",
    "TW_DAILY539",
    "TW_LOTTO649",
    "TW_PICK3",
    "TW_PICK4",
    "TW_SUPER_LOTTO638",
)


def _seed(game_code: str) -> int:
    return int(
        hashlib.sha256(
            f"weekly|{game_code}|single-fixed-v1".encode()
        ).hexdigest()[:10],
        16,
    )


def needs_rebuild() -> bool:
    with SessionLocal() as db:
        for game_code in GAME_CODES:
            game = db.scalar(select(Game).where(Game.game_code == game_code))
            if game is None:
                continue
            data_game = game
            if game.parent_game_code:
                parent = db.scalar(
                    select(Game).where(Game.game_code == game.parent_game_code)
                )
                if parent is not None:
                    data_game = parent
            latest_draw_id = db.scalar(
                select(Draw.id)
                .where(
                    Draw.game_id == data_game.id,
                    Draw.source_status == "official",
                )
                .order_by(Draw.draw_date.desc(), Draw.draw_no.desc())
                .limit(1)
            )
            latest_replay_end_id = next(
                (
                    replay.end_draw_id
                    for replay in db.scalars(
                select(ReplayRun)
                .join(
                    GenerationPreset,
                    ReplayRun.preset_id == GenerationPreset.id,
                )
                .where(
                    ReplayRun.game_id == game.id,
                    ReplayRun.status == "completed",
                    GenerationPreset.preset_code == "VIDEO_FIVE_STEP_V1",
                )
                .order_by(ReplayRun.completed_at.desc(), ReplayRun.id.desc())
                    )
                    if replay.tickets_per_draw == 1
                    and replay.config_json.get("cadence") == "week"
                ),
                None,
            )
            if latest_draw_id is not None and latest_replay_end_id != latest_draw_id:
                return True
    return False


def main() -> None:
    results: list[dict[str, object]] = []
    for game_code in GAME_CODES:
        with SessionLocal() as db:
            game = db.scalar(select(Game).where(Game.game_code == game_code))
            if game is None:
                results.append({"game_code": game_code, "status": "game_not_found"})
                continue
            data_game = game
            if game.parent_game_code:
                parent = db.scalar(
                    select(Game).where(Game.game_code == game.parent_game_code)
                )
                if parent is not None:
                    data_game = parent
            official_count = int(
                db.scalar(
                    select(func.count(Draw.id)).where(
                        Draw.game_id == data_game.id,
                        Draw.source_status == "official",
                    )
                )
                or 0
            )
            draw_count = official_count or int(
                db.scalar(
                    select(func.count(Draw.id)).where(Draw.game_id == data_game.id)
                )
                or 0
            )
            lookback = 20
            replay_periods = 1000 if game.game_type == "high_frequency" else 104
            replay_periods = min(replay_periods, max(0, draw_count - lookback))
            if replay_periods < 10:
                results.append(
                    {
                        "game_code": game_code,
                        "status": "insufficient_data",
                        "draw_count": draw_count,
                    }
                )
                continue
            request = ReplayRequest(
                game_code=game_code,
                start_index=draw_count - replay_periods,
                end_index=draw_count - 1,
                lookback_count=lookback,
                tickets_per_draw=1,
                random_seed=_seed(game_code),
                baseline_repetitions=20,
                strategy="video",
                cadence="week",
                star_count=6,
            )
            created = create_replay_job(db, request)
            run_uuid = str(created["run_uuid"])
        run_replay_job(run_uuid)
        with SessionLocal() as db:
            status = get_replay(db, run_uuid)
        results.append(
            {
                "game_code": game_code,
                "run_uuid": run_uuid,
                "status": status["status"],
                "summary": status["summary"],
            }
        )
        print(
            f"{game_code}: {status['status']} "
            f"({status['progress_current']}/{status['progress_total']})",
            flush=True,
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "WEEKLY_SINGLE_FIXED_V1",
        "future_data_used": False,
        "results": results,
    }
    output = REPORT_DIR / "replay" / "weekly_replay_latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(str(output))


if __name__ == "__main__":
    main()
