from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.core.exceptions import NumerisError
from app.core.paths import REPORT_DIR
from app.models.api_models import ReplayRequest
from app.models.database_models import (
    Draw,
    Game,
    GenerationPreset,
    Job,
    ReplayDrawResult,
    ReplayRun,
    Ruleset,
)
from app.services.analytics.core import analyze_numbers
from app.services.generation.generators import UnorderedCombinationGenerator

T = TypeVar("T")


def replay_input_draws[T](draws: list[T], target_index: int, lookback: int) -> list[T]:
    """只回傳目標期之前的資料，是防止未來資料洩漏的單一入口。"""
    if target_index <= 0 or target_index >= len(draws):
        raise ValueError("目標期索引超出範圍")
    return draws[max(0, target_index - lookback) : target_index]


def create_replay_job(db: Session, request: ReplayRequest) -> dict[str, Any]:
    game = db.scalar(select(Game).where(Game.game_code == request.game_code))
    if game is None:
        raise NumerisError("GAME_NOT_FOUND", "找不到指定彩種")
    if game.game_type not in {"unordered_unique_numbers", "derived_game"}:
        raise NumerisError("REPLAY_UNSUPPORTED", "第一版歷史逐期模擬支援一般無序號碼遊戲")
    preset = db.scalar(
        select(GenerationPreset).where(GenerationPreset.preset_code == "VIDEO_FIVE_STEP_V1")
    )
    draws = list(
        db.scalars(
            select(Draw).where(Draw.game_id == game.id).order_by(Draw.draw_date, Draw.draw_no)
        )
    )
    end_index = request.end_index if request.end_index is not None else len(draws) - 1
    if request.start_index >= len(draws) or end_index >= len(draws):
        raise NumerisError(
            "REPLAY_RANGE",
            "模擬期別範圍超出現有資料",
            {"draw_count": len(draws)},
        )
    run_uuid = str(uuid.uuid4())
    replay = ReplayRun(
        run_uuid=run_uuid,
        game_id=game.id,
        preset_id=preset.id,
        start_draw_id=draws[request.start_index].id,
        end_draw_id=draws[end_index].id,
        lookback_count=request.lookback_count,
        tickets_per_draw=request.tickets_per_draw,
        seed_policy="base_seed_plus_target_index",
        baseline_repetitions=request.baseline_repetitions,
        config_json=request.model_dump(),
        status="pending",
        progress_current=0,
        progress_total=end_index - request.start_index + 1,
    )
    job = Job(
        job_uuid=run_uuid,
        job_type="replay",
        status="pending",
        progress_current=0,
        progress_total=replay.progress_total,
        message="等待執行歷史逐期模擬",
        parameters_json=request.model_dump(),
    )
    db.add_all([replay, job])
    db.commit()
    return {"run_uuid": run_uuid, "job_uuid": run_uuid, "status": "pending"}


def run_replay_job(run_uuid: str) -> None:
    db = SessionLocal()
    try:
        replay = db.scalar(select(ReplayRun).where(ReplayRun.run_uuid == run_uuid))
        job = db.scalar(select(Job).where(Job.job_uuid == run_uuid))
        if replay is None or job is None:
            return
        replay.status = job.status = "running"
        replay.started_at = job.started_at = datetime.now(UTC)
        job.message = "正在執行歷史逐期模擬"
        db.commit()
        _execute_replay(db, replay, job)
    except Exception as exc:
        db.rollback()
        replay = db.scalar(select(ReplayRun).where(ReplayRun.run_uuid == run_uuid))
        job = db.scalar(select(Job).where(Job.job_uuid == run_uuid))
        if replay:
            replay.status = "failed"
        if job:
            job.status = "failed"
            job.message = f"歷史逐期模擬失敗：{exc}"
            job.completed_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def _execute_replay(db: Session, replay: ReplayRun, job: Job) -> None:
    game = db.get(Game, replay.game_id)
    ruleset = db.scalar(
        select(Ruleset).where(Ruleset.game_id == replay.game_id).order_by(Ruleset.id.desc())
    )
    draws = list(
        db.scalars(
            select(Draw)
            .where(Draw.game_id == replay.game_id)
            .options(selectinload(Draw.numbers))
            .order_by(Draw.draw_date, Draw.draw_no)
        )
    )
    start_index = next(index for index, draw in enumerate(draws) if draw.id == replay.start_draw_id)
    end_index = next(index for index, draw in enumerate(draws) if draw.id == replay.end_draw_id)
    pool = ruleset.config_json["pools"][0]
    aggregate_method: Counter[int] = Counter()
    aggregate_uniform: Counter[int] = Counter()
    aggregate_structured: Counter[int] = Counter()
    rng = np.random.Generator(np.random.PCG64(int(replay.config_json.get("random_seed", 0))))
    highest_hit = 0

    for progress, target_index in enumerate(range(start_index, end_index + 1), 1):
        db.refresh(job)
        if job.status == "cancelled":
            replay.status = "cancelled"
            replay.completed_at = datetime.now(UTC)
            db.commit()
            return
        input_draws = replay_input_draws(draws, target_index, replay.lookback_count)
        sample_numbers = [_main_numbers(draw, str(pool["code"])) for draw in input_draws]
        metrics = analyze_numbers(
            sample_numbers,
            int(pool["min"]),
            int(pool["max"]),
            int(pool["draw_count"]),
            [draw.draw_no for draw in input_draws],
        )
        previous = sample_numbers[-1]
        target_numbers = set(_main_numbers(draws[target_index], str(pool["code"])))
        seed = int(replay.config_json.get("random_seed", 0)) + target_index
        generator = UnorderedCombinationGenerator(seed)
        method_candidates, _ = generator.generate(
            replay.tickets_per_draw,
            pool=pool,
            metrics=metrics,
            previous_numbers=previous,
            max_attempts=30000,
        )
        method_hits = [
            len(set(candidate.primary_numbers) & target_numbers) for candidate in method_candidates
        ]
        uniform_hits: list[int] = []
        structured_hits: list[int] = []
        for _ in range(replay.tickets_per_draw):
            uniform_numbers = rng.choice(
                np.arange(int(pool["min"]), int(pool["max"]) + 1),
                size=int(pool["pick_count"]),
                replace=False,
            )
            uniform_hits.append(len(set(int(value) for value in uniform_numbers) & target_numbers))
        structured_generator = UnorderedCombinationGenerator(seed + 1_000_000)
        structured_candidates, _ = structured_generator.generate(
            replay.tickets_per_draw,
            pool=pool,
            metrics=metrics,
            previous_numbers=previous,
            max_attempts=30000,
            temperature_constraint=False,
        )
        structured_hits.extend(
            len(set(candidate.primary_numbers) & target_numbers)
            for candidate in structured_candidates
        )
        aggregate_method.update(method_hits)
        aggregate_uniform.update(uniform_hits)
        aggregate_structured.update(structured_hits)
        highest_hit = max(highest_hit, *method_hits)
        db.add(
            ReplayDrawResult(
                replay_run_id=replay.id,
                target_draw_id=draws[target_index].id,
                cutoff_draw_id=input_draws[-1].id,
                generated_ticket_count=len(method_candidates),
                hit_distribution_json=dict(Counter(method_hits)),
                baseline_distribution_json={
                    "uniform": dict(Counter(uniform_hits)),
                    "structured": dict(Counter(structured_hits)),
                },
                result_json={
                    "target_draw_no": draws[target_index].draw_no,
                    "analysis_draw_ids": [draw.id for draw in input_draws],
                    "future_data_used": False,
                },
            )
        )
        replay.progress_current = job.progress_current = progress
        job.message = f"已完成 {progress}/{replay.progress_total} 期"
        db.commit()

    total_tickets = sum(aggregate_method.values())
    average_hits = (
        sum(hits * count for hits, count in aggregate_method.items()) / total_tickets
        if total_tickets
        else 0.0
    )
    summary = {
        "game_code": game.game_code,
        "simulated_draws": replay.progress_total,
        "tickets_per_draw": replay.tickets_per_draw,
        "total_tickets": total_tickets,
        "hit_distribution": dict(sorted(aggregate_method.items())),
        "uniform_baseline_distribution": dict(sorted(aggregate_uniform.items())),
        "structured_baseline_distribution": dict(sorted(aggregate_structured.items())),
        "highest_single_ticket_hit": highest_hit,
        "average_hits": round(average_hits, 6),
        "future_data_used": False,
        "roi_calculated": False,
        "roi_note": "未載入完整且已驗證的逐期獎金資料，因此不計算成本、獎金或回收率。",
    }
    report_path = _write_replay_report(replay.run_uuid, summary)
    replay.result_summary_json = summary
    replay.report_path = str(report_path)
    replay.status = job.status = "completed"
    replay.completed_at = job.completed_at = datetime.now(UTC)
    job.result_json = summary
    job.message = "歷史逐期模擬完成"
    db.commit()


def _main_numbers(draw: Draw, pool_code: str) -> list[int]:
    return [
        number.number_value
        for number in draw.numbers
        if number.pool_code == pool_code and not number.is_special
    ]


def _write_replay_report(run_uuid: str, summary: dict[str, Any]) -> Path:
    path = REPORT_DIR / "replay" / f"replay_{run_uuid}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    pretty = json.dumps(summary, ensure_ascii=False, indent=2)
    path.write_text(
        "<!doctype html><html lang='zh-Hant'><meta charset='utf-8'>"
        "<title>Numeris 歷史逐期模擬報告</title>"
        "<style>body{font-family:system-ui;max-width:960px;margin:40px auto;line-height:1.6}"
        "pre{background:#f4f6f8;padding:20px;border-radius:10px}</style>"
        "<h1>Numeris 歷史逐期模擬報告</h1>"
        "<p>本報告僅為描述統計，不代表未來結果。</p>"
        f"<pre>{pretty}</pre></html>",
        encoding="utf-8",
    )
    return path


def get_replay(db: Session, run_uuid: str) -> dict[str, Any]:
    replay = db.scalar(select(ReplayRun).where(ReplayRun.run_uuid == run_uuid))
    if replay is None:
        raise NumerisError("REPLAY_NOT_FOUND", "找不到歷史逐期模擬紀錄")
    return {
        "run_uuid": replay.run_uuid,
        "status": replay.status,
        "progress_current": replay.progress_current,
        "progress_total": replay.progress_total,
        "summary": replay.result_summary_json,
        "report_path": replay.report_path,
    }
