from __future__ import annotations

import hashlib
import itertools
import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.core.exceptions import GenerationError
from app.models.api_models import GenerationRequest, SimpleGenerationRequest
from app.models.database_models import (
    AuditLog,
    Draw,
    EvaluationRun,
    Game,
    GenerationPreset,
    GenerationRun,
    ReplayDrawResult,
    ReplayRun,
    Ruleset,
    TicketResult,
)
from app.services.analytics.core import analyze_numbers, calculate_structure
from app.services.bootstrap import canonical_hash
from app.services.evaluation.service import evaluate_generation_run, get_evaluation
from app.services.generation.anchor import (
    as_utc,
    draw_arrived_after_lock,
    verify_recommendation_anchor,
)
from app.services.generation.generators import (
    Candidate,
    UnorderedCombinationGenerator,
    recommended_coverage_target,
)
from app.services.generation.service import (
    _draws_for_game,
    _next_draw_no,
    _pool_draws,
    _save_candidates,
    create_generation_run,
    get_game_and_ruleset,
    lock_generation_run,
    serialize_generation_run,
)
from app.services.replay.anchor import (
    WALK_FORWARD_ANCHOR_SCOPE,
    WALK_FORWARD_ANCHOR_VERSION,
    calculate_walk_forward_anchor,
)

SIMPLE_METHOD_REVISION = "VIDEO_FIVE_STEP_V1_AUDITED_20260724"
COVERAGE_METHOD_REVISION = "COVERAGE_OPTIMIZED_V1_20260724"
WEEKLY_METHOD_REVISION = "WEEKLY_SINGLE_V1_20260724"
TAIPEI = ZoneInfo("Asia/Taipei")


def _method_revision(mode: str) -> str:
    if mode == "weekly":
        return WEEKLY_METHOD_REVISION
    return COVERAGE_METHOD_REVISION if mode == "coverage" else SIMPLE_METHOD_REVISION


def _week_key(value: datetime) -> str:
    iso = value.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _current_week_key() -> str:
    return _week_key(datetime.now(TAIPEI))


def _seed_for(game_code: str, anchor_key: int | str, mode: str) -> int:
    raw = (
        f"{game_code}|{anchor_key}|{mode}|{__version__}|"
        f"{_method_revision(mode)}"
    ).encode()
    return int(hashlib.sha256(raw).hexdigest()[:12], 16)


def _recent_simple_run(
    db: Session,
    game_id: int,
    cutoff_id: int,
    mode: str,
    star_count: int,
    week_key: str | None = None,
) -> GenerationRun | None:
    conditions = [
        GenerationRun.game_id == game_id,
        GenerationRun.locked.is_(True),
    ]
    if mode != "weekly":
        conditions.append(GenerationRun.cutoff_draw_id == cutoff_id)
    runs = list(
        db.scalars(
            select(GenerationRun)
            .where(*conditions)
            .order_by(GenerationRun.id.desc())
            .limit(100)
        )
    )
    for run in runs:
        config = dict(run.config_json or {})
        if (
            config.get("simple_interface") is True
            and config.get("simple_mode") == mode
            and config.get("method_revision") == _method_revision(mode)
            and int(config.get("star_count", star_count)) == star_count
            and (mode != "weekly" or config.get("weekly_key") == week_key)
            and verify_recommendation_anchor(db, run)
        ):
            return run
    return None


def _mark_simple_run(
    db: Session,
    run_uuid: str,
    mode: str,
    star_count: int,
    week_key: str | None = None,
) -> dict[str, Any]:
    run = db.scalar(select(GenerationRun).where(GenerationRun.run_uuid == run_uuid))
    if run is None:
        raise GenerationError("RUN_NOT_FOUND", "找不到剛建立的推薦紀錄")
    config = dict(run.config_json)
    config.update(
        {
            "simple_interface": True,
            "simple_mode": mode,
            "star_count": star_count,
            "method_revision": _method_revision(mode),
        }
    )
    if mode == "weekly":
        first_ticket = run.tickets[0] if run.tickets else None
        pools: dict[str, list[int]] = defaultdict(list)
        if first_ticket is not None:
            for number in first_ticket.numbers:
                pools[number.pool_code].append(int(number.number_value))
        weekly_numbers = {
            pool: numbers for pool, numbers in sorted(pools.items())
        }
        config.update(
            {
                "weekly_key": week_key,
                "weekly_single": True,
                "coverage_target_hits": 1,
                "weekly_number_anchor": canonical_hash(
                    {
                        "game_id": run.game_id,
                        "week": week_key,
                        "numbers": weekly_numbers,
                    }
                ),
            }
        )
    run.config_json = config
    run.config_hash = canonical_hash(config)
    db.commit()
    return lock_generation_run(db, run_uuid)


def _create_wheel_run(
    db: Session,
    game: Game,
    ruleset: Ruleset,
    wheel_size: int,
    seed: int,
) -> dict[str, Any]:
    if game.game_type not in {"unordered_unique_numbers", "derived_game"}:
        raise GenerationError("WHEEL_NOT_SUPPORTED", "此彩種不適用包牌排列組合")
    draws = _draws_for_game(db, game, 100)
    if not draws:
        raise GenerationError("NO_DATA", "此彩種尚無可用開獎資料")
    analysis_draws = draws[-20:]
    primary_pool = dict(ruleset.config_json["pools"][0])
    pick_count = int(primary_pool["pick_count"])
    if wheel_size <= pick_count:
        raise GenerationError("WHEEL_SIZE", "包牌號碼數必須大於單式選取數")
    combination_count = math.comb(wheel_size, pick_count)
    if combination_count > 100:
        raise GenerationError(
            "WHEEL_TOO_LARGE",
            "這個包牌會超過100組，請選擇較少的核心號碼",
            {"combination_count": combination_count},
        )
    samples, draw_nos = _pool_draws(
        analysis_draws,
        str(primary_pool["code"]),
    )
    metrics = analyze_numbers(
        samples,
        int(primary_pool["min"]),
        int(primary_pool["max"]),
        int(primary_pool["draw_count"]),
        draw_nos,
    )
    wheel_pool = dict(primary_pool)
    wheel_pool["pick_count"] = wheel_size
    generator = UnorderedCombinationGenerator(seed)
    base_candidates, diagnostics = generator.generate(
        1,
        pool=wheel_pool,
        metrics=metrics,
        previous_numbers=samples[-1],
        allowed_odd_counts=list(range(wheel_size + 1)),
        allowed_high_counts=list(range(wheel_size + 1)),
        ac_min=None,
        ac_max=None,
        max_overlap=wheel_size,
        include_ac=False,
    )
    wheel_numbers = base_candidates[0].primary_numbers
    candidates: list[Candidate] = []
    for combination in itertools.combinations(wheel_numbers, pick_count):
        numbers = list(combination)
        structure = calculate_structure(
            numbers,
            int(primary_pool["high_boundary"]),
            primary_pool["zones"],
            samples[-1],
            include_ac=game.supports_ac,
        )
        candidates.append(
            Candidate(
                pools={str(primary_pool["code"]): numbers},
                structure=structure,
                preference_score=base_candidates[0].preference_score,
                diversity_score=0.0,
                explanation={
                    "wheel_numbers": wheel_numbers,
                    "wheel_size": wheel_size,
                    "message": (
                        f"由{wheel_size}個核心號碼展開的第{len(candidates) + 1}組單式；"
                        "所有排列組合刻意高度重疊。"
                    ),
                },
            )
        )
    preset = db.scalar(
        select(GenerationPreset).where(GenerationPreset.preset_code == "VIDEO_FIVE_STEP_V1")
    )
    if preset is None:
        raise GenerationError("PRESET_NOT_FOUND", "找不到內建選號模式")
    now = datetime.now(UTC)
    config: dict[str, Any] = {
        "game_code": game.game_code,
        "simple_interface": True,
        "simple_mode": f"wheel{wheel_size}",
        "wheel_size": wheel_size,
        "wheel_numbers": wheel_numbers,
        "combination_count": combination_count,
        "lookback_count": len(analysis_draws),
        "structure_lookback_count": len(draws),
        "method_code": "VIDEO_FIVE_STEP_V1",
        "method_revision": SIMPLE_METHOD_REVISION,
        "method_steps": {
            "step_1": f"最近{len(analysis_draws)}期，截止{draws[-1].draw_no}",
            "step_2": "冷熱溫百分位均衡混合",
            "step_3": "奇偶、大小及區間結構篩選",
            "step_4": "包牌核心不套用AC；展開單式仍顯示AC",
            "step_5": f"{wheel_size}碼核心完整展開{combination_count}組",
        },
        "random_seed": seed,
        "star_count": pick_count,
    }
    run = GenerationRun(
        run_uuid=str(uuid.uuid4()),
        game_id=game.id,
        target_draw_no=_next_draw_no(draws[-1].draw_no),
        cutoff_draw_id=draws[-1].id,
        preset_id=preset.id,
        requested_ticket_count=combination_count,
        generated_ticket_count=combination_count,
        random_seed=seed,
        config_json=config,
        config_hash=canonical_hash(config),
        app_version=__version__,
        locked=False,
        locked_at=None,
        started_at=now,
        completed_at=now,
        status="completed",
        diagnostic_json={
            **diagnostics,
            "wheel_size": wheel_size,
            "combination_count": combination_count,
            "constraints_relaxed": False,
        },
    )
    db.add(run)
    db.flush()
    _save_candidates(db, run, candidates, False)
    db.add(
        AuditLog(
            action="generation.simple_wheel_created",
            entity_type="generation_run",
            entity_id=run.run_uuid,
            detail_json={
                "seed": seed,
                "wheel_size": wheel_size,
                "combination_count": combination_count,
            },
        )
    )
    db.commit()
    payload = lock_generation_run(db, run.run_uuid)
    payload["wheel_numbers"] = wheel_numbers
    payload["combination_count"] = combination_count
    return payload


def create_simple_recommendation(
    db: Session, request: SimpleGenerationRequest
) -> dict[str, Any]:
    game, ruleset = get_game_and_ruleset(db, request.game_code)
    latest_draws = _draws_for_game(db, game, 1)
    if not latest_draws:
        raise GenerationError("NO_DATA", "此彩種尚無可用資料")
    latest = latest_draws[-1]
    week_key = _current_week_key() if request.mode == "weekly" else None
    if not request.refresh:
        existing = _recent_simple_run(
            db,
            game.id,
            latest.id,
            request.mode,
            request.star_count,
            week_key,
        )
        if existing is not None:
            payload = serialize_generation_run(db, existing.run_uuid)
            payload["reused"] = True
            return payload
    elif request.mode == "weekly":
        existing = _recent_simple_run(
            db,
            game.id,
            latest.id,
            request.mode,
            request.star_count,
            week_key,
        )
        if existing is not None:
            payload = serialize_generation_run(db, existing.run_uuid)
            payload["reused"] = True
            return payload
    seed = request.random_seed
    if seed is None:
        seed = _seed_for(
            game.game_code,
            week_key if week_key is not None else latest.id,
            request.mode,
        )
        if request.refresh and request.mode != "weekly":
            seed += int(datetime.now(UTC).timestamp() * 1000)
    if request.mode == "weekly":
        recent_draws = _draws_for_game(db, game, 100)
        prior_week_draws = [
            draw
            for draw in recent_draws
            if _week_key(
                datetime.combine(
                    draw.draw_date,
                    datetime.min.time(),
                    tzinfo=TAIPEI,
                )
            )
            != week_key
        ]
        cutoff = prior_week_draws[-1] if prior_week_draws else latest
        payload = create_generation_run(
            db,
            GenerationRequest(
                game_code=game.game_code,
                ticket_count=1,
                lookback_count=20,
                random_seed=seed,
                preset_code="VIDEO_FIVE_STEP_V1",
                target_draw_no=_next_draw_no(latest.draw_no),
                cutoff_draw_no=cutoff.draw_no,
                max_overlap=None,
                star_count=request.star_count,
            ),
        )
        return _mark_simple_run(
            db,
            str(payload["run_uuid"]),
            request.mode,
            request.star_count,
            week_key,
        )
    if request.mode.startswith("wheel"):
        wheel_size = int(request.mode.removeprefix("wheel"))
        return _create_wheel_run(db, game, ruleset, wheel_size, seed)
    primary_pick = (
        request.star_count
        if game.game_type == "high_frequency"
        else int(ruleset.config_json["pools"][0]["pick_count"])
    )
    if request.mode == "coverage":
        target_hits = recommended_coverage_target(
            game.game_type,
            primary_pick,
        )
        payload = create_generation_run(
            db,
            GenerationRequest(
                game_code=game.game_code,
                ticket_count=request.ticket_count,
                lookback_count=20,
                random_seed=seed,
                preset_code="COVERAGE_OPTIMIZED_V1",
                max_overlap=max(0, target_hits - 1),
                star_count=request.star_count,
                allowed_odd_counts=list(range(primary_pick + 1)),
                allowed_high_counts=list(range(primary_pick + 1)),
                ac_min=None,
                ac_max=None,
                selection_strategy="coverage",
                coverage_target_hits=target_hits,
                use_temperature_preference=False,
            ),
        )
        return _mark_simple_run(
            db,
            str(payload["run_uuid"]),
            request.mode,
            request.star_count,
        )
    max_overlap = 5 if game.game_type == "high_frequency" else 3
    payload = create_generation_run(
        db,
        GenerationRequest(
            game_code=game.game_code,
            ticket_count=request.ticket_count,
            lookback_count=20,
            random_seed=seed,
            max_overlap=max_overlap,
            star_count=request.star_count,
        ),
    )
    return _mark_simple_run(db, str(payload["run_uuid"]), request.mode, request.star_count)


def _sync_available_evaluations(db: Session, game: Game) -> int:
    if game.parent_game_code:
        return 0
    runs = list(
        db.scalars(
            select(GenerationRun)
            .where(
                GenerationRun.game_id == game.id,
                GenerationRun.locked.is_(True),
            )
            .order_by(GenerationRun.id.desc())
            .limit(100)
        )
    )
    synced = 0
    for run in runs:
        if not verify_recommendation_anchor(db, run):
            continue
        exists = db.scalar(
            select(EvaluationRun.id).where(EvaluationRun.generation_run_id == run.id)
        )
        if exists is not None:
            continue
        draw = db.scalar(
            select(Draw).where(
                Draw.game_id == game.id,
                Draw.draw_no == run.target_draw_no,
            )
        )
        if draw is not None and draw_arrived_after_lock(run, draw):
            evaluate_generation_run(db, run.run_uuid)
            synced += 1
    return synced


def _empty_performance_bucket() -> dict[str, int]:
    return {
        "evaluated_runs": 0,
        "target_hit_draws": 0,
        "tickets": 0,
        "tickets_with_hit": 0,
        "exact_tickets": 0,
        "hit_numbers": 0,
        "checked_numbers": 0,
        "best_hit": 0,
    }


def _add_performance_results(
    bucket: dict[str, int],
    results: list[TicketResult],
    pick_count: int,
    target_hits: int,
) -> None:
    bucket["evaluated_runs"] += 1
    bucket["tickets"] += len(results)
    bucket["checked_numbers"] += len(results) * pick_count
    for result in results:
        hits = int(result.main_hit_count)
        bucket["hit_numbers"] += hits
        bucket["best_hit"] = max(bucket["best_hit"], hits)
        if hits > 0:
            bucket["tickets_with_hit"] += 1
        if hits >= pick_count:
            bucket["exact_tickets"] += 1
    if results and max(int(result.main_hit_count) for result in results) >= target_hits:
        bucket["target_hit_draws"] += 1


def _merge_performance(
    target: dict[str, int],
    source: dict[str, int],
) -> None:
    for key in (
        "evaluated_runs",
        "target_hit_draws",
        "tickets",
        "tickets_with_hit",
        "exact_tickets",
        "hit_numbers",
        "checked_numbers",
    ):
        target[key] += source[key]
    target["best_hit"] = max(target["best_hit"], source["best_hit"])


def _performance_rates(bucket: dict[str, int]) -> dict[str, Any]:
    tickets = bucket["tickets"]
    checked_numbers = bucket["checked_numbers"]
    any_hit_ticket_rate = (
        round(bucket["tickets_with_hit"] / tickets * 100, 2)
        if tickets
        else None
    )
    return {
        **bucket,
        "target_hit_rate": (
            round(bucket["target_hit_draws"] / bucket["evaluated_runs"] * 100, 2)
            if bucket["evaluated_runs"]
            else None
        ),
        # Keep the original key for API compatibility. The explicit alias prevents
        # the value from being mistaken for the percentage of correct numbers.
        "ticket_hit_rate": any_hit_ticket_rate,
        "any_hit_ticket_rate": any_hit_ticket_rate,
        "number_accuracy": (
            round(bucket["hit_numbers"] / checked_numbers * 100, 2)
            if checked_numbers
            else None
        ),
    }


def _rate_delta(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return round(float(left) - float(right), 2)


def _add_replay_distribution(
    bucket: dict[str, int],
    distribution: dict[str, Any],
    pick_count: int,
    target_hits: int,
) -> None:
    parsed = {int(hits): int(count) for hits, count in distribution.items()}
    tickets = sum(parsed.values())
    bucket["evaluated_runs"] += 1
    bucket["tickets"] += tickets
    bucket["checked_numbers"] += tickets * pick_count
    bucket["tickets_with_hit"] += sum(
        count for hits, count in parsed.items() if hits > 0
    )
    bucket["exact_tickets"] += sum(
        count for hits, count in parsed.items() if hits >= pick_count
    )
    bucket["hit_numbers"] += sum(hits * count for hits, count in parsed.items())
    if parsed and max(parsed) >= target_hits:
        bucket["target_hit_draws"] += 1
    if parsed:
        bucket["best_hit"] = max(bucket["best_hit"], max(parsed))


def _theoretical_uniform_rates(
    db: Session,
    game: Game,
    pick_count: int,
    target_hits: int,
    tickets_per_draw: int,
) -> dict[str, float]:
    ruleset = db.scalar(
        select(Ruleset)
        .where(Ruleset.game_id == game.id)
        .order_by(Ruleset.id.desc())
    )
    if ruleset is None:
        return {}
    pool = dict(ruleset.config_json["pools"][0])
    if game.game_type == "ordered_digits":
        batch_rate = min(1.0, tickets_per_draw / (10**pick_count))
        return {
            "target_hit_rate": round(batch_rate * 100, 2),
            "number_accuracy": 10.0,
        }
    population = int(pool["max"]) - int(pool["min"]) + 1
    drawn = int(pool["draw_count"])
    denominator = math.comb(population, pick_count)
    single_target_rate = sum(
        math.comb(drawn, hits)
        * math.comb(population - drawn, pick_count - hits)
        / denominator
        for hits in range(target_hits, min(drawn, pick_count) + 1)
        if pick_count - hits <= population - drawn
    )
    batch_rate = 1 - (1 - single_target_rate) ** tickets_per_draw
    return {
        "target_hit_rate": round(batch_rate * 100, 2),
        "number_accuracy": round(drawn / population * 100, 2),
    }


def _replay_performance_payload(
    db: Session,
    game: Game,
) -> dict[str, Any] | None:
    replay = next(
        (
            candidate
            for candidate in db.scalars(
            select(ReplayRun)
            .join(GenerationPreset, ReplayRun.preset_id == GenerationPreset.id)
            .where(
                ReplayRun.game_id == game.id,
                ReplayRun.status == "completed",
                GenerationPreset.preset_code == "VIDEO_FIVE_STEP_V1",
            )
            .order_by(ReplayRun.completed_at.desc(), ReplayRun.id.desc())
            )
            if candidate.tickets_per_draw == 1
            and candidate.config_json.get("cadence") == "week"
        ),
        None,
    )
    if replay is None:
        return None
    rows = db.execute(
        select(ReplayDrawResult, Draw)
        .join(Draw, ReplayDrawResult.target_draw_id == Draw.id)
        .where(ReplayDrawResult.replay_run_id == replay.id)
        .order_by(Draw.draw_date, Draw.draw_no)
    ).all()
    if not rows:
        return None
    weekly_buckets: dict[str, dict[str, int]] = defaultdict(
        _empty_performance_bucket
    )
    weekly_meta: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "draw_dates": [],
            "period_anchors": [],
            "anchor_created_at": [],
        }
    )
    overall = _empty_performance_bucket()
    uniform_overall = _empty_performance_bucket()
    structured_overall = _empty_performance_bucket()
    periods: list[dict[str, Any]] = []
    weekly_samples: dict[str, dict[str, Any]] = {}
    replay_pick_count = 1
    replay_target_hits = 1
    anchors_changed = False
    retrospective_anchor_time = datetime.now(UTC).isoformat()
    for result, draw in rows:
        detail = dict(result.result_json or {})
        predicted_tickets = list(detail.get("predicted_tickets") or [])
        fixed_prediction = (
            [int(number) for number in predicted_tickets[0]]
            if predicted_tickets
            else [int(number) for number in detail.get("predicted_numbers", [])]
        )
        actual_numbers = [
            int(number) for number in detail.get("actual_numbers", [])
        ]
        if game.game_type == "ordered_digits":
            hit_positions = [
                index
                for index, (predicted, actual) in enumerate(
                    zip(fixed_prediction, actual_numbers, strict=False)
                )
                if predicted == actual
            ]
            comparison_hits = [
                fixed_prediction[index] for index in hit_positions
            ]
        else:
            hit_positions = []
            comparison_hits = sorted(
                set(fixed_prediction) & set(actual_numbers)
            )
        detail.update(
            {
                "predicted_numbers": fixed_prediction,
                "display_ticket_index": 1,
                "comparison_hit_numbers": comparison_hits,
                "comparison_hit_positions": hit_positions,
                "comparison_hit_count": len(comparison_hits),
                "comparison_number_count": len(fixed_prediction),
                "comparison_hit_rate": (
                    round(len(comparison_hits) / len(fixed_prediction) * 100, 2)
                    if fixed_prediction
                    else None
                ),
                "prediction_source": "每週唯一1組無未來資料回測",
            }
        )
        calculated_anchor = calculate_walk_forward_anchor(
            replay,
            result,
            detail,
        )
        stored_anchor = detail.get("walk_forward_anchor")
        if stored_anchor is None:
            detail.update(
                {
                    "walk_forward_anchor": calculated_anchor,
                    "walk_forward_anchor_version": WALK_FORWARD_ANCHOR_VERSION,
                    "walk_forward_anchor_scope": WALK_FORWARD_ANCHOR_SCOPE,
                    "walk_forward_anchor_created_at": retrospective_anchor_time,
                }
            )
            result.result_json = detail
            stored_anchor = calculated_anchor
            anchors_changed = True
        anchor_valid = (
            stored_anchor == calculated_anchor
            and detail.get("walk_forward_anchor_version")
            == WALK_FORWARD_ANCHOR_VERSION
            and detail.get("walk_forward_anchor_scope")
            == WALK_FORWARD_ANCHOR_SCOPE
        )
        if not anchor_valid:
            continue
        pick_count = int(detail.get("comparison_number_count") or 1)
        target_hits = int(
            detail.get("coverage_target_hits")
            or 1
        )
        replay_pick_count = pick_count
        replay_target_hits = target_hits
        period_stats = _empty_performance_bucket()
        _add_replay_distribution(
            period_stats,
            dict(result.hit_distribution_json or {}),
            pick_count,
            target_hits,
        )
        iso = draw.draw_date.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        weekly_meta[week]["draw_dates"].append(draw.draw_date.isoformat())
        weekly_meta[week]["period_anchors"].append(stored_anchor)
        weekly_meta[week]["anchor_created_at"].append(
            detail.get("walk_forward_anchor_created_at")
        )
        _merge_performance(weekly_buckets[week], period_stats)
        _merge_performance(overall, period_stats)
        baseline_distributions = dict(result.baseline_distribution_json or {})
        _add_replay_distribution(
            uniform_overall,
            dict(baseline_distributions.get("uniform") or {}),
            pick_count,
            target_hits,
        )
        _add_replay_distribution(
            structured_overall,
            dict(baseline_distributions.get("structured") or {}),
            pick_count,
            target_hits,
        )
        period_payload = {
            "draw_no": draw.draw_no,
            "draw_date": draw.draw_date.isoformat(),
            "run_uuid": replay.run_uuid,
            "prediction_mode": detail.get("prediction_mode", "replay"),
            "prediction_source": detail.get(
                "prediction_source",
                "影片五步法逐期回放第1組",
            ),
            "predicted_numbers": detail.get("predicted_numbers", []),
            "actual_numbers": detail.get("actual_numbers", []),
            "actual_special_numbers": detail.get(
                "actual_special_numbers",
                [],
            ),
            "comparison_hit_numbers": detail.get(
                "comparison_hit_numbers",
                [],
            ),
            "comparison_hit_positions": detail.get(
                "comparison_hit_positions",
                [],
            ),
            "comparison_hit_count": detail.get("comparison_hit_count", 0),
            "comparison_number_count": pick_count,
            "comparison_hit_rate": detail.get("comparison_hit_rate"),
            "coverage_target_hits": target_hits,
            "target_achieved": bool(
                detail.get("target_achieved")
                if "target_achieved" in detail
                else period_stats["target_hit_draws"]
            ),
            "walk_forward_anchor": stored_anchor,
            "walk_forward_anchor_created_at": detail.get(
                "walk_forward_anchor_created_at"
            ),
            "walk_forward_anchor_scope": WALK_FORWARD_ANCHOR_SCOPE,
            **_performance_rates(period_stats),
        }
        periods.append(period_payload)
        weekly_samples[week] = period_payload
    if anchors_changed:
        db.commit()
    weekly = [
        {
            "week": week,
            "first_draw_date": min(weekly_meta[week]["draw_dates"]),
            "last_draw_date": max(weekly_meta[week]["draw_dates"]),
            "walk_forward_anchor": canonical_hash(
                {
                    "anchor_version": WALK_FORWARD_ANCHOR_VERSION,
                    "scope": WALK_FORWARD_ANCHOR_SCOPE,
                    "game_code": game.game_code,
                    "week": week,
                    "period_anchors": sorted(
                        weekly_meta[week]["period_anchors"]
                    ),
                }
            ),
            "anchor_created_at": max(
                value
                for value in weekly_meta[week]["anchor_created_at"]
                if value
            ),
            "anchor_scope": WALK_FORWARD_ANCHOR_SCOPE,
            "future_data_used": False,
            "sample_draw_no": weekly_samples[week]["draw_no"],
            "sample_draw_date": weekly_samples[week]["draw_date"],
            "predicted_numbers": weekly_samples[week]["predicted_numbers"],
            "actual_numbers": weekly_samples[week]["actual_numbers"],
            "actual_special_numbers": weekly_samples[week][
                "actual_special_numbers"
            ],
            "comparison_hit_numbers": weekly_samples[week][
                "comparison_hit_numbers"
            ],
            "comparison_hit_positions": weekly_samples[week][
                "comparison_hit_positions"
            ],
            "sample_hit_count": weekly_samples[week]["comparison_hit_count"],
            "sample_number_count": weekly_samples[week][
                "comparison_number_count"
            ],
            **_performance_rates(weekly_buckets[week]),
        }
        for week in sorted(weekly_buckets, reverse=True)[:10]
    ]
    recent_periods = list(reversed(periods[-10:]))
    recent_10 = _empty_performance_bucket()
    for period in periods[-10:]:
        stats = _empty_performance_bucket()
        stats.update(
            {
                key: int(period[key])
                for key in stats
                if period.get(key) is not None
            }
        )
        _merge_performance(recent_10, stats)
    latest_week = weekly[0] if weekly else {
        "week": None,
        **_performance_rates(_empty_performance_bucket()),
    }
    method_rates = _performance_rates(overall)
    uniform_rates = _performance_rates(uniform_overall)
    structured_rates = _performance_rates(structured_overall)
    tickets_per_draw = (
        round(overall["tickets"] / overall["evaluated_runs"])
        if overall["evaluated_runs"]
        else 10
    )
    theoretical_uniform = _theoretical_uniform_rates(
        db,
        game,
        replay_pick_count,
        replay_target_hits,
        tickets_per_draw,
    )
    uniform_rates.update(theoretical_uniform)
    return {
        "weekly": weekly,
        "recent_periods": recent_periods,
        "summary": {
            "recent_10": _performance_rates(recent_10),
            "latest_week": latest_week,
            "overall": method_rates,
        },
        "baselines": {
            "method": method_rates,
            "uniform_random": uniform_rates,
            "structure_only": structured_rates,
            "number_accuracy_delta_vs_random": _rate_delta(
                method_rates["number_accuracy"],
                uniform_rates["number_accuracy"],
            ),
            "any_hit_delta_vs_random": _rate_delta(
                method_rates["any_hit_ticket_rate"],
                uniform_rates["any_hit_ticket_rate"],
            ),
            "target_hit_rate_delta_vs_random": _rate_delta(
                method_rates["target_hit_rate"],
                uniform_rates["target_hit_rate"],
            ),
            "same_ticket_count": method_rates["tickets"]
            == uniform_rates["tickets"]
            == structured_rates["tickets"],
            "uniform_rate_source": "exact_combinatorial_probability",
        },
        "source": str(
            dict(replay.result_summary_json or {}).get(
                "calculation_method",
                "VIDEO_FIVE_STEP_V1",
            )
        ),
        "replay_run_uuid": replay.run_uuid,
        "future_data_used": False,
        "anchor_version": WALK_FORWARD_ANCHOR_VERSION,
        "anchor_scope": WALK_FORWARD_ANCHOR_SCOPE,
        "anchor_created_at": max(
            (
                period.get("walk_forward_anchor_created_at")
                for period in periods
                if period.get("walk_forward_anchor_created_at")
            ),
            default=None,
        ),
    }


def _comparison_payload(
    run: GenerationRun,
    actual_draw: Draw,
    ruleset: Ruleset | None,
    game: Game,
) -> dict[str, Any]:
    primary_pool_code = "main"
    if ruleset is not None:
        primary_pool_code = str(ruleset.config_json["pools"][0]["code"])
    wheel_numbers = run.config_json.get("wheel_numbers")
    if isinstance(wheel_numbers, list) and wheel_numbers:
        predicted_numbers = [int(number) for number in wheel_numbers]
        prediction_source = "包牌核心號碼"
    else:
        first_ticket = run.tickets[0] if run.tickets else None
        predicted_numbers = (
            [
                int(number.number_value)
                for number in first_ticket.numbers
                if number.pool_code == primary_pool_code
            ]
            if first_ticket is not None
            else []
        )
        prediction_source = "每週唯一定錨組合"
    actual_main = [
        int(number.number_value)
        for number in sorted(
            (
                number
                for number in actual_draw.numbers
                if number.pool_code == primary_pool_code and not number.is_special
            ),
            key=lambda number: (
                number.draw_order if number.draw_order is not None else 999,
                number.sorted_order if number.sorted_order is not None else 999,
                number.id,
            ),
        )
    ]
    actual_special = [
        int(number.number_value)
        for number in actual_draw.numbers
        if number.is_special
    ]
    if game.game_type == "ordered_digits":
        hit_positions = [
            index
            for index, (predicted, actual) in enumerate(
                zip(predicted_numbers, actual_main, strict=False)
            )
            if predicted == actual
        ]
        hit_numbers = [predicted_numbers[index] for index in hit_positions]
        hit_count = len(hit_positions)
    else:
        hit_positions = []
        hit_numbers = sorted(set(predicted_numbers) & set(actual_main))
        hit_count = len(hit_numbers)
    hit_rate = (
        round(hit_count / len(predicted_numbers) * 100, 2)
        if predicted_numbers
        else None
    )
    return {
        "run_uuid": run.run_uuid,
        "prediction_mode": str(run.config_json.get("simple_mode", "single")),
        "prediction_source": prediction_source,
        "predicted_numbers": predicted_numbers,
        "actual_numbers": actual_main,
        "actual_special_numbers": actual_special,
        "comparison_hit_numbers": hit_numbers,
        "comparison_hit_positions": hit_positions,
        "comparison_hit_count": hit_count,
        "comparison_number_count": len(predicted_numbers),
        "comparison_hit_rate": hit_rate,
    }


def _performance_payload(db: Session, game: Game) -> dict[str, Any]:
    evaluations = list(
        db.scalars(
            select(EvaluationRun)
            .join(GenerationRun, EvaluationRun.generation_run_id == GenerationRun.id)
            .where(
                GenerationRun.game_id == game.id,
                EvaluationRun.status == "completed",
            )
            .order_by(EvaluationRun.id.desc())
        )
    )
    # A user can generate several recommendations for the same target draw.
    # Counting the best or newest one after the result is known would be
    # cherry-picking, so only the earliest valid pre-draw anchor is eligible.
    canonical_by_draw: dict[int, tuple[EvaluationRun, GenerationRun, Draw]] = {}
    for evaluation in evaluations:
        run = db.get(GenerationRun, evaluation.generation_run_id)
        actual_draw = db.get(Draw, evaluation.actual_draw_id)
        if (
            run is None
            or actual_draw is None
            or run.config_json.get("simple_mode") != "weekly"
            or actual_draw.draw_no != run.target_draw_no
            or not verify_recommendation_anchor(db, run)
            or not draw_arrived_after_lock(run, actual_draw)
        ):
            continue
        evaluated_at = as_utc(evaluation.evaluated_at)
        draw_ingested_at = as_utc(actual_draw.created_at)
        if (
            evaluated_at is None
            or draw_ingested_at is None
            or evaluated_at < draw_ingested_at
        ):
            continue
        current = canonical_by_draw.get(actual_draw.id)
        if current is None:
            canonical_by_draw[actual_draw.id] = (evaluation, run, actual_draw)
            continue
        current_run = current[1]
        run_key = (as_utc(run.locked_at) or datetime.max.replace(tzinfo=UTC), run.id)
        current_key = (
            as_utc(current_run.locked_at) or datetime.max.replace(tzinfo=UTC),
            current_run.id,
        )
        if run_key < current_key:
            canonical_by_draw[actual_draw.id] = (evaluation, run, actual_draw)

    weekly_buckets: dict[str, dict[str, int]] = defaultdict(
        _empty_performance_bucket
    )
    periods: list[dict[str, Any]] = []
    overall = _empty_performance_bucket()
    ordered_evaluations = sorted(
        canonical_by_draw.values(),
        key=lambda item: (item[2].draw_date, item[2].draw_no),
    )
    for evaluation, run, actual_draw in ordered_evaluations:
        iso = actual_draw.draw_date.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        ruleset = db.get(Ruleset, evaluation.ruleset_id)
        pick_count = 1
        if ruleset is not None:
            pick_count = int(ruleset.config_json["pools"][0]["pick_count"])
        if game.game_type == "high_frequency":
            pick_count = int(run.config_json.get("star_count", pick_count))
        target_hits = int(
            run.config_json.get("coverage_target_hits")
            or recommended_coverage_target(game.game_type, pick_count)
        )
        results = list(
            db.scalars(
                select(TicketResult).where(TicketResult.evaluation_run_id == evaluation.id)
            )
        )
        _add_performance_results(
            weekly_buckets[week],
            results,
            pick_count,
            target_hits,
        )
        _add_performance_results(overall, results, pick_count, target_hits)
        period_stats = _empty_performance_bucket()
        _add_performance_results(
            period_stats,
            results,
            pick_count,
            target_hits,
        )
        locked_at = as_utc(run.locked_at)
        draw_ingested_at = as_utc(actual_draw.created_at)
        periods.append(
            {
                "draw_no": actual_draw.draw_no,
                "draw_date": actual_draw.draw_date.isoformat(),
                **_comparison_payload(
                    run,
                    actual_draw,
                    ruleset,
                    game,
                ),
                **_performance_rates(period_stats),
                "coverage_target_hits": target_hits,
                "target_achieved": bool(period_stats["target_hit_draws"]),
                "best_hit_count": period_stats["best_hit"],
                "recommendation_anchor": run.config_json.get(
                    "recommendation_anchor"
                ),
                "locked_at": locked_at.isoformat() if locked_at else None,
                "draw_ingested_at": (
                    draw_ingested_at.isoformat() if draw_ingested_at else None
                ),
            },
        )

    weekly: list[dict[str, Any]] = []
    for week in sorted(weekly_buckets, reverse=True)[:10]:
        weekly.append(
            {
                "week": week,
                **_performance_rates(weekly_buckets[week]),
            }
        )
    recent_10 = _empty_performance_bucket()
    recent_periods = list(reversed(periods[-10:]))
    for period in periods[-10:]:
        stats = _empty_performance_bucket()
        stats.update(
            {
                key: int(period[key])
                for key in stats
                if period.get(key) is not None
            }
        )
        _merge_performance(recent_10, stats)
    latest_week = weekly[0] if weekly else {
        "week": None,
        **_performance_rates(_empty_performance_bucket()),
    }
    return {
        "weekly": weekly,
        "recent_periods": recent_periods,
        "summary": {
            "recent_10": _performance_rates(recent_10),
            "latest_week": latest_week,
            "overall": _performance_rates(overall),
        },
        "baselines": None,
        "source": "ANCHORED_POST_DRAW_EVALUATION",
        "replay_run_uuid": None,
        "future_data_used": False,
        "anchored_sample_count": overall["evaluated_runs"],
    }


def simple_dashboard(db: Session, game_code: str) -> dict[str, Any]:
    game, ruleset = get_game_and_ruleset(db, game_code)
    _sync_available_evaluations(db, game)
    draws = _draws_for_game(db, game, 1)
    latest = draws[-1] if draws else None
    query_game = game
    if game.parent_game_code:
        parent = db.scalar(select(Game).where(Game.game_code == game.parent_game_code))
        if parent is not None:
            query_game = parent
    official_count = int(
        db.scalar(
            select(func.count(Draw.id)).where(
                Draw.game_id == query_game.id,
                Draw.source_status == "official",
            )
        )
        or 0
    )
    fixture_count = int(
        db.scalar(
            select(func.count(Draw.id)).where(
                Draw.game_id == query_game.id,
                Draw.source_status == "fixture",
            )
        )
        or 0
    )
    runs_statement = (
        select(GenerationRun)
        .join(Draw, GenerationRun.cutoff_draw_id == Draw.id)
        .where(
            GenerationRun.game_id == game.id,
            GenerationRun.locked.is_(True),
        )
        .order_by(GenerationRun.id.desc())
        .limit(50)
    )
    if official_count:
        runs_statement = runs_statement.where(Draw.source_status == "official")
    runs = [
        run
        for run in db.scalars(runs_statement)
        if verify_recommendation_anchor(db, run)
    ][:8]
    records: list[dict[str, Any]] = []
    for run in runs:
        if run.config_json.get("simple_mode") != "weekly":
            continue
        payload = serialize_generation_run(db, run.run_uuid)
        evaluation = get_evaluation(db, run.run_uuid)
        if (
            evaluation.get("status") == "completed"
            and evaluation.get("actual_draw_no") != run.target_draw_no
        ):
            evaluation = {
                "run_uuid": run.run_uuid,
                "status": "期別不符",
                "results": [],
            }
        payload["evaluation"] = evaluation
        records.append(payload)
    latest_simple = next(
        (
            record
            for record in records
            if record["config"].get("simple_interface") is True
            and record["config"].get("simple_mode") == "weekly"
            and record["config"].get("weekly_key") == _current_week_key()
        ),
        None,
    )
    primary_pick = int(ruleset.config_json["pools"][0]["pick_count"])
    default_coverage_target = 1
    wheel_modes: list[int] = []
    performance = _performance_payload(db, game)
    historical_review = _replay_performance_payload(db, game)
    return {
        "game": {
            "game_code": game.game_code,
            "display_name": game.display_name_zh_tw,
            "game_type": game.game_type,
            "primary_pick_count": primary_pick,
            "coverage_target_hits": default_coverage_target,
            "wheel_modes": wheel_modes,
            "ruleset_verified": ruleset.verified,
        },
        "data": {
            "official_count": official_count,
            "fixture_count": fixture_count,
            "latest_draw_no": latest.draw_no if latest else None,
            "latest_draw_date": latest.draw_date.isoformat() if latest else None,
            "latest_source_status": latest.source_status if latest else None,
        },
        "latest_recommendation": latest_simple,
        "records": records,
        "weekly_performance": performance["weekly"],
        "recent_periods": performance["recent_periods"],
        "performance_summary": performance["summary"],
        "performance_baselines": performance.get("baselines"),
        "performance_source": performance.get("source"),
        "performance_replay_run_uuid": performance.get("replay_run_uuid"),
        "anchored_sample_count": performance.get("anchored_sample_count", 0),
        "future_data_used": performance.get("future_data_used", False),
        "historical_weekly_review": {
            "available": historical_review is not None,
            "weeks": historical_review["weekly"] if historical_review else [],
            "summary": historical_review["summary"] if historical_review else None,
            "replay_run_uuid": (
                historical_review.get("replay_run_uuid")
                if historical_review
                else None
            ),
            "anchor_version": (
                historical_review.get("anchor_version")
                if historical_review
                else None
            ),
            "anchor_scope": (
                historical_review.get("anchor_scope")
                if historical_review
                else None
            ),
            "anchor_created_at": (
                historical_review.get("anchor_created_at")
                if historical_review
                else None
            ),
            "future_data_used": (
                historical_review.get("future_data_used")
                if historical_review
                else False
            ),
            "note": (
                "近10週每週只固定1組號碼，並只使用該週開始前的資料重建推薦；"
                "預測組合與輸入資料"
                "已建立回測定錨；定錨建立時間晚於歷史開獎，因此只代表可重現的"
                "無未來資料回測，不冒充當時已存在的實戰鎖定。每週會隨官方資料"
                "更新向前滾動，且不計入上方實戰達標率。"
            ),
        },
        "metric_definitions": {
            "target_hit_rate": (
                "有命中期數 ÷ 開獎後已驗證的每週唯一組合；"
                "有命中＝該組至少命中1個主要號碼"
            ),
            "number_accuracy": (
                "每週唯一組合命中的主要號碼總數 ÷ 該組全部檢查號碼數"
            ),
            "any_hit_ticket_rate": (
                "至少命中1個主要號碼的週組合數 ÷ 全部已驗證週組合數"
            ),
            "period_comparison": (
                "每週表只顯示開獎前鎖定的唯一1組，絕不在開獎後換號"
            ),
        },
        "metric_note": (
            "這裡只顯示實戰定錨紀錄，不混入歷史回放。推薦產生時會把目標期別、"
            "資料截止期、鎖定時間與每週唯一1組寫入 SHA-256 定錨；只有開獎資料在"
            "鎖定後才寫入、定錨驗證成功且期別完全相同，才會計分。"
            "同一週固定後不能換號；有命中率＝唯一1組至少命中1碼的實戰比例。"
            "尚未累積合格樣本時一律顯示「等待驗證」，不以回放數字代替。"
        ),
    }
