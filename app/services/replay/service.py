from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
from sqlalchemy import and_, func, or_, select
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
from app.services.analytics.core import analyze_numbers, analyze_ordered_positions
from app.services.generation.generators import (
    BingoGenerator,
    MultiPoolGenerator,
    OrderedDigitGenerator,
    UnorderedCombinationGenerator,
)
from app.services.generation.service import _historical_ac_range

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
    preset = db.scalar(
        select(GenerationPreset).where(GenerationPreset.preset_code == "VIDEO_FIVE_STEP_V1")
    )
    if preset is None:
        raise NumerisError("PRESET_NOT_FOUND", "找不到影片五步選號法")
    data_game = game
    if game.parent_game_code:
        parent = db.scalar(select(Game).where(Game.game_code == game.parent_game_code))
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
    source_status = "official" if official_count else None
    draw_filters = [Draw.game_id == data_game.id]
    if source_status:
        draw_filters.append(Draw.source_status == source_status)
    draw_count = int(db.scalar(select(func.count(Draw.id)).where(*draw_filters)) or 0)
    end_index = request.end_index if request.end_index is not None else draw_count - 1
    if (
        request.start_index >= draw_count
        or end_index >= draw_count
        or end_index < request.start_index
    ):
        raise NumerisError(
            "REPLAY_RANGE",
            "模擬期別範圍超出現有資料",
            {"draw_count": draw_count},
        )
    ordered_ids = (
        select(Draw.id)
        .where(*draw_filters)
        .order_by(Draw.draw_date, Draw.draw_no)
    )
    start_draw_id = db.scalar(ordered_ids.offset(request.start_index).limit(1))
    end_draw_id = db.scalar(ordered_ids.offset(end_index).limit(1))
    if start_draw_id is None or end_draw_id is None:
        raise NumerisError("REPLAY_RANGE", "找不到指定逐期模擬範圍")
    config = request.model_dump()
    config["source_status"] = source_status
    config["data_game_code"] = data_game.game_code
    config["star_count"] = 6
    run_uuid = str(uuid.uuid4())
    replay = ReplayRun(
        run_uuid=run_uuid,
        game_id=game.id,
        preset_id=preset.id,
        start_draw_id=start_draw_id,
        end_draw_id=end_draw_id,
        lookback_count=request.lookback_count,
        tickets_per_draw=request.tickets_per_draw,
        seed_policy="base_seed_plus_target_index",
        baseline_repetitions=request.baseline_repetitions,
        config_json=config,
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
    if game is None:
        raise NumerisError("GAME_NOT_FOUND", "找不到逐期模擬彩種")
    data_game = game
    if game.parent_game_code:
        parent = db.scalar(select(Game).where(Game.game_code == game.parent_game_code))
        if parent is not None:
            data_game = parent
    ruleset = db.scalar(
        select(Ruleset).where(Ruleset.game_id == replay.game_id).order_by(Ruleset.id.desc())
    )
    if ruleset is None:
        raise NumerisError("RULESET_NOT_FOUND", "找不到逐期模擬彩種規則")
    start_draw = db.get(Draw, replay.start_draw_id)
    end_draw = db.get(Draw, replay.end_draw_id)
    if start_draw is None or end_draw is None:
        raise NumerisError("REPLAY_RANGE", "找不到逐期模擬起迄期別")
    source_status = replay.config_json.get("source_status")
    common_filters = [Draw.game_id == data_game.id]
    if source_status:
        common_filters.append(Draw.source_status == source_status)
    history = list(
        db.scalars(
            select(Draw)
            .where(
                *common_filters,
                or_(
                    Draw.draw_date < start_draw.draw_date,
                    and_(
                        Draw.draw_date == start_draw.draw_date,
                        Draw.draw_no < start_draw.draw_no,
                    ),
                ),
            )
            .options(selectinload(Draw.numbers))
            .order_by(Draw.draw_date.desc(), Draw.draw_no.desc())
            .limit(replay.lookback_count)
        )
    )
    history.reverse()
    targets = list(
        db.scalars(
            select(Draw)
            .where(
                *common_filters,
                or_(
                    Draw.draw_date > start_draw.draw_date,
                    and_(
                        Draw.draw_date == start_draw.draw_date,
                        Draw.draw_no >= start_draw.draw_no,
                    ),
                ),
                or_(
                    Draw.draw_date < end_draw.draw_date,
                    and_(
                        Draw.draw_date == end_draw.draw_date,
                        Draw.draw_no <= end_draw.draw_no,
                    ),
                ),
            )
            .options(selectinload(Draw.numbers))
            .order_by(Draw.draw_date, Draw.draw_no)
        )
    )
    if len(history) < 2 or not targets:
        raise NumerisError("REPLAY_RANGE", "逐期模擬資料不足")
    draws = history + targets
    start_index = len(history)
    end_index = len(draws) - 1
    pool = dict(ruleset.config_json["pools"][0])
    if game.game_type == "high_frequency":
        pool["pick_count"] = int(replay.config_json.get("star_count", 6))
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
        target_number_list = _main_numbers(draws[target_index], str(pool["code"]))
        target_numbers = set(target_number_list)
        target_special_numbers = [
            number.number_value
            for number in draws[target_index].numbers
            if number.is_special
        ]
        seed = int(replay.config_json.get("random_seed", 0)) + target_index
        ac_min, ac_max = (
            _historical_ac_range(
                input_draws,
                str(pool["code"]),
                int(pool["pick_count"]),
            )
            if game.supports_ac
            else (None, None)
        )
        if game.game_type == "multi_pool":
            metrics_by_pool: dict[str, list[dict[str, Any]]] = {}
            previous_by_pool: dict[str, list[int]] = {}
            for configured_pool in ruleset.config_json["pools"]:
                code = str(configured_pool["code"])
                samples = [_main_numbers(draw, code) for draw in input_draws]
                if not samples or not samples[-1]:
                    continue
                metrics_by_pool[code] = analyze_numbers(
                    samples,
                    int(configured_pool["min"]),
                    int(configured_pool["max"]),
                    int(configured_pool["draw_count"]),
                    [draw.draw_no for draw in input_draws],
                )
                previous_by_pool[code] = samples[-1]
            generator = MultiPoolGenerator(seed)
            method_candidates, _ = generator.generate(
                replay.tickets_per_draw,
                pools=ruleset.config_json["pools"],
                metrics_by_pool=metrics_by_pool,
                previous_by_pool=previous_by_pool,
                ac_min=ac_min,
                ac_max=ac_max,
                max_attempts=30000,
            )
        elif game.game_type == "ordered_digits":
            generator = OrderedDigitGenerator(seed)
            method_candidates, _ = generator.generate(
                count=replay.tickets_per_draw,
                pool=pool,
                previous_numbers=previous,
                metrics_by_position=analyze_ordered_positions(
                    sample_numbers,
                    int(pool["min"]),
                    int(pool["max"]),
                    int(pool["pick_count"]),
                    [draw.draw_no for draw in input_draws],
                ),
            )
        elif game.game_type == "high_frequency":
            generator = BingoGenerator(seed)
            method_candidates, _ = generator.generate(
                replay.tickets_per_draw,
                pool=pool,
                metrics=metrics,
                previous_numbers=previous,
                max_attempts=30000,
            )
        else:
            generator = UnorderedCombinationGenerator(seed)
            method_candidates, _ = generator.generate(
                replay.tickets_per_draw,
                pool=pool,
                metrics=metrics,
                previous_numbers=previous,
                ac_min=ac_min,
                ac_max=ac_max,
                max_attempts=30000,
            )
        if game.game_type == "ordered_digits":
            method_hits = [
                sum(
                    predicted == actual
                    for predicted, actual in zip(
                        candidate.primary_numbers,
                        target_number_list,
                        strict=False,
                    )
                )
                for candidate in method_candidates
            ]
        else:
            method_hits = [
                len(set(candidate.primary_numbers) & target_numbers)
                for candidate in method_candidates
            ]
        uniform_hits: list[int] = []
        structured_hits: list[int] = []
        for _ in range(replay.tickets_per_draw):
            uniform_numbers = [
                int(value)
                for value in rng.choice(
                    np.arange(int(pool["min"]), int(pool["max"]) + 1),
                    size=int(pool["pick_count"]),
                    replace=game.game_type == "ordered_digits",
                )
            ]
            if game.game_type == "ordered_digits":
                uniform_hits.append(
                    sum(
                        predicted == actual
                        for predicted, actual in zip(
                            uniform_numbers,
                            target_number_list,
                            strict=False,
                        )
                    )
                )
            else:
                uniform_hits.append(len(set(uniform_numbers) & target_numbers))
        if game.game_type == "multi_pool":
            structured_generator = MultiPoolGenerator(seed + 1_000_000)
            structured_candidates, _ = structured_generator.generate(
                replay.tickets_per_draw,
                pools=ruleset.config_json["pools"],
                metrics_by_pool=metrics_by_pool,
                previous_by_pool=previous_by_pool,
                ac_min=ac_min,
                ac_max=ac_max,
                max_attempts=30000,
                temperature_constraint=False,
                use_temperature_preference=False,
            )
            structured_hits.extend(
                len(set(candidate.primary_numbers) & target_numbers)
                for candidate in structured_candidates
            )
        elif game.game_type == "ordered_digits":
            structured_generator = OrderedDigitGenerator(seed + 1_000_000)
            structured_candidates, _ = structured_generator.generate(
                replay.tickets_per_draw,
                pool=pool,
                previous_numbers=previous,
                metrics_by_position=analyze_ordered_positions(
                    sample_numbers,
                    int(pool["min"]),
                    int(pool["max"]),
                    int(pool["pick_count"]),
                    [draw.draw_no for draw in input_draws],
                ),
                use_temperature_preference=False,
            )
            structured_hits.extend(
                sum(
                    predicted == actual
                    for predicted, actual in zip(
                        candidate.primary_numbers,
                        target_number_list,
                        strict=False,
                    )
                )
                for candidate in structured_candidates
            )
        elif game.game_type in {
            "unordered_unique_numbers",
            "derived_game",
            "high_frequency",
        }:
            structured_generator = UnorderedCombinationGenerator(seed + 1_000_000)
            structured_candidates, _ = structured_generator.generate(
                replay.tickets_per_draw,
                pool=pool,
                metrics=metrics,
                previous_numbers=previous,
                max_attempts=30000,
                temperature_constraint=False,
                use_temperature_preference=False,
            )
            structured_hits.extend(
                len(set(candidate.primary_numbers) & target_numbers)
                for candidate in structured_candidates
            )
        else:
            structured_hits.extend(uniform_hits)
        aggregate_method.update(method_hits)
        aggregate_uniform.update(uniform_hits)
        aggregate_structured.update(structured_hits)
        highest_hit = max(highest_hit, *method_hits)
        predicted_tickets = [
            [int(number) for number in candidate.primary_numbers]
            for candidate in method_candidates
        ]
        first_prediction = predicted_tickets[0] if predicted_tickets else []
        if game.game_type == "ordered_digits":
            hit_positions = [
                index
                for index, (predicted, actual) in enumerate(
                    zip(first_prediction, target_number_list, strict=False)
                )
                if predicted == actual
            ]
            hit_numbers = [first_prediction[index] for index in hit_positions]
        else:
            hit_positions = []
            hit_numbers = sorted(set(first_prediction) & target_numbers)
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
                    "target_draw_date": draws[target_index].draw_date.isoformat(),
                    "analysis_draw_ids": [draw.id for draw in input_draws],
                    "predicted_tickets": predicted_tickets,
                    "predicted_numbers": first_prediction,
                    "actual_numbers": target_number_list,
                    "actual_special_numbers": target_special_numbers,
                    "comparison_hit_numbers": hit_numbers,
                    "comparison_hit_positions": hit_positions,
                    "comparison_hit_count": len(hit_numbers),
                    "comparison_number_count": len(first_prediction),
                    "comparison_hit_rate": (
                        round(len(hit_numbers) / len(first_prediction) * 100, 2)
                        if first_prediction
                        else None
                    ),
                    "method_hits": method_hits,
                    "prediction_source": "影片五步法逐期回放第1組",
                    "prediction_mode": "replay",
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
        "calculation_method": "VIDEO_FIVE_STEP_V1",
        "source_status": source_status,
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
