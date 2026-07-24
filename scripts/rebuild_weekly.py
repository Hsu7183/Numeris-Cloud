from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.paths import REPORT_DIR
from app.models.api_models import ReplayRequest
from app.models.database_models import Draw, Game
from app.services.replay.service import (
    create_replay_job,
    get_replay,
    run_replay_job,
)

GAME_CODES = (
    "HK_MARKSIX",
    "TW_39MATCH",
    "TW_49MATCH",
    "TW_BINGO",
    "TW_DAILY539",
    "TW_LOTTO649",
    "TW_PICK3",
    "TW_PICK4",
    "TW_SUPER_LOTTO638",
)


def _seed(game_code: str) -> int:
    return int(hashlib.sha256(f"weekly|{game_code}|v1".encode()).hexdigest()[:10], 16)


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
                tickets_per_draw=10,
                random_seed=_seed(game_code),
                baseline_repetitions=20,
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
        "method": "VIDEO_FIVE_STEP_V1",
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
