from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.core.paths import PROJECT_ROOT, ensure_directories
from app.models.api_models import SimpleGenerationRequest
from app.models.database_models import Game, Job
from app.services.bootstrap import initialize_catalog
from app.services.data_sources.official import create_update_job, run_update_job
from app.services.simple_dashboard import (
    create_simple_recommendation,
    simple_dashboard,
)

STATUS_PATH = PROJECT_ROOT / "data" / "cache" / "startup_refresh_latest.json"


def prepare_database() -> None:
    ensure_directories()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        initialize_catalog(db)


def refresh_official_data() -> dict[str, Any]:
    with SessionLocal() as db:
        created = create_update_job(db, "all")
    job_uuid = created["job_uuid"]
    run_update_job(job_uuid)
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.job_uuid == job_uuid))
        if job is None:
            raise RuntimeError("找不到啟動更新工作")
        return {
            "job_uuid": job.job_uuid,
            "status": job.status,
            "message": job.message,
            "result": dict(job.result_json or {}),
        }


def active_game_codes() -> list[str]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Game.game_code)
                .where(Game.active.is_(True))
                .order_by(Game.market_code, Game.id)
            )
        )


def refresh_weekly_recommendations() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for game_code in active_game_codes():
        with SessionLocal() as db:
            try:
                simple_dashboard(db, game_code)
                payload = create_simple_recommendation(
                    db,
                    SimpleGenerationRequest(
                        game_code=game_code,
                        mode="weekly",
                        ticket_count=1,
                        refresh=False,
                    ),
                )
                config = dict(payload.get("config") or {})
                tickets = list(payload.get("tickets") or [])
                results.append(
                    {
                        "game_code": game_code,
                        "status": "ready",
                        "weekly_key": config.get("weekly_key"),
                        "target_draw_no": payload.get("target_draw_no"),
                        "cutoff_draw_no": payload.get("cutoff_draw_no"),
                        "recommendation_anchor": payload.get("recommendation_anchor"),
                        "numbers": tickets[0].get("pools", {}) if tickets else {},
                        "reused": bool(payload.get("reused", False)),
                    }
                )
            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "game_code": game_code,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
    return results


def source_failures(update_result: dict[str, Any]) -> list[str]:
    result = update_result.get("result")
    if not isinstance(result, dict):
        return []
    return [
        name
        for name in ("taiwan", "hongkong")
        if isinstance(result.get(name), dict) and result[name].get("error")
    ]


def write_status(
    official_update: dict[str, Any],
    recommendations: list[dict[str, Any]],
) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "completed_at": datetime.now(UTC).isoformat(),
                "official_update": official_update,
                "recommendations": recommendations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    print("[Numeris] Preparing the local database...")
    prepare_database()

    print("[Numeris] Downloading the latest official draw results...")
    try:
        official_update = refresh_official_data()
    except Exception as exc:
        official_update = {
            "status": "failed",
            "message": str(exc),
            "result": {},
        }

    failures = source_failures(official_update)
    if official_update.get("status") == "failed":
        print("[Numeris] Official update failed; continuing with verified cached data.")
    elif failures:
        print(
            "[Numeris] Some official sources are temporarily unavailable: "
            + ", ".join(failures)
        )
    else:
        print("[Numeris] Official draw data is up to date.")

    print("[Numeris] Checking results and calculating this week's numbers...")
    recommendations = refresh_weekly_recommendations()
    ready = [item for item in recommendations if item["status"] == "ready"]
    failed = [item for item in recommendations if item["status"] == "failed"]
    for item in ready:
        state = "kept" if item["reused"] else "created"
        print(
            f"[Numeris] {item['game_code']}: {item['weekly_key']} "
            f"{state}, target {item['target_draw_no']}."
        )
    for item in failed:
        print(f"[Numeris] {item['game_code']}: recommendation failed ({item['error']}).")

    write_status(official_update, recommendations)
    print(f"[Numeris] {len(ready)}/{len(recommendations)} products are ready.")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
