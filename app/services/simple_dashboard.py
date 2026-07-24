from __future__ import annotations

import hashlib
import itertools
import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

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
from app.services.generation.generators import Candidate, UnorderedCombinationGenerator
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


def _seed_for(game_code: str, cutoff_id: int, mode: str) -> int:
    raw = f"{game_code}|{cutoff_id}|{mode}|{__version__}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:12], 16)


def _recent_simple_run(
    db: Session,
    game_id: int,
    cutoff_id: int,
    mode: str,
    star_count: int,
) -> GenerationRun | None:
    runs = list(
        db.scalars(
            select(GenerationRun)
            .where(
                GenerationRun.game_id == game_id,
                GenerationRun.cutoff_draw_id == cutoff_id,
                GenerationRun.locked.is_(True),
            )
            .order_by(GenerationRun.id.desc())
            .limit(30)
        )
    )
    for run in runs:
        if (
            run.config_json.get("simple_interface") is True
            and run.config_json.get("simple_mode") == mode
            and int(run.config_json.get("star_count", star_count)) == star_count
        ):
            return run
    return None


def _mark_simple_run(
    db: Session,
    run_uuid: str,
    mode: str,
    star_count: int,
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
    samples, draw_nos = _pool_draws(draws, str(primary_pool["code"]))
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
        "lookback_count": min(100, len(draws)),
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
        locked=True,
        locked_at=now,
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
    payload = serialize_generation_run(db, run.run_uuid)
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
    if not request.refresh:
        existing = _recent_simple_run(
            db,
            game.id,
            latest.id,
            request.mode,
            request.star_count,
        )
        if existing is not None:
            payload = serialize_generation_run(db, existing.run_uuid)
            payload["reused"] = True
            return payload
    seed = request.random_seed
    if seed is None:
        seed = _seed_for(game.game_code, latest.id, request.mode)
        if request.refresh:
            seed += int(datetime.now(UTC).timestamp() * 1000)
    if request.mode.startswith("wheel"):
        wheel_size = int(request.mode.removeprefix("wheel"))
        return _create_wheel_run(db, game, ruleset, wheel_size, seed)
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
        exists = db.scalar(
            select(EvaluationRun.id).where(EvaluationRun.generation_run_id == run.id)
        )
        if exists is not None:
            continue
        draw_exists = db.scalar(
            select(Draw.id).where(
                Draw.game_id == game.id,
                Draw.draw_no == run.target_draw_no,
            )
        )
        if draw_exists is not None:
            evaluate_generation_run(db, run.run_uuid)
            synced += 1
    return synced


def _empty_performance_bucket() -> dict[str, int]:
    return {
        "evaluated_runs": 0,
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


def _merge_performance(
    target: dict[str, int],
    source: dict[str, int],
) -> None:
    for key in (
        "evaluated_runs",
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
    return {
        **bucket,
        "ticket_hit_rate": (
            round(bucket["tickets_with_hit"] / tickets * 100, 2)
            if tickets
            else None
        ),
        "number_accuracy": (
            round(bucket["hit_numbers"] / checked_numbers * 100, 2)
            if checked_numbers
            else None
        ),
    }


def _add_replay_distribution(
    bucket: dict[str, int],
    distribution: dict[str, Any],
    pick_count: int,
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
    if parsed:
        bucket["best_hit"] = max(bucket["best_hit"], max(parsed))


def _replay_performance_payload(
    db: Session,
    game: Game,
) -> dict[str, Any] | None:
    replay = db.scalar(
        select(ReplayRun)
        .join(GenerationPreset, ReplayRun.preset_id == GenerationPreset.id)
        .where(
            ReplayRun.game_id == game.id,
            ReplayRun.status == "completed",
            GenerationPreset.preset_code == "VIDEO_FIVE_STEP_V1",
        )
        .order_by(ReplayRun.completed_at.desc(), ReplayRun.id.desc())
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
    overall = _empty_performance_bucket()
    periods: list[dict[str, Any]] = []
    for result, draw in rows:
        detail = dict(result.result_json or {})
        pick_count = int(detail.get("comparison_number_count") or 1)
        period_stats = _empty_performance_bucket()
        _add_replay_distribution(
            period_stats,
            dict(result.hit_distribution_json or {}),
            pick_count,
        )
        iso = draw.draw_date.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        _merge_performance(weekly_buckets[week], period_stats)
        _merge_performance(overall, period_stats)
        periods.append(
            {
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
                **_performance_rates(period_stats),
            }
        )
    weekly = [
        {"week": week, **_performance_rates(weekly_buckets[week])}
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
    return {
        "weekly": weekly,
        "recent_periods": recent_periods,
        "summary": {
            "recent_10": _performance_rates(recent_10),
            "latest_week": latest_week,
            "overall": _performance_rates(overall),
        },
        "source": "VIDEO_FIVE_STEP_V1_REPLAY",
        "replay_run_uuid": replay.run_uuid,
        "future_data_used": False,
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
        prediction_source = "推薦第1組"
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
    replay_payload = _replay_performance_payload(db, game)
    if replay_payload is not None:
        return replay_payload
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
    weekly_buckets: dict[str, dict[str, int]] = defaultdict(
        _empty_performance_bucket
    )
    period_buckets: dict[str, dict[str, Any]] = {}
    overall = _empty_performance_bucket()
    for evaluation in evaluations:
        run = db.get(GenerationRun, evaluation.generation_run_id)
        if run is None:
            continue
        actual_draw = db.get(Draw, evaluation.actual_draw_id)
        if actual_draw is None or actual_draw.draw_no != run.target_draw_no:
            continue
        iso = actual_draw.draw_date.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        ruleset = db.get(Ruleset, evaluation.ruleset_id)
        pick_count = 1
        if ruleset is not None:
            pick_count = int(ruleset.config_json["pools"][0]["pick_count"])
        if game.game_type == "high_frequency":
            pick_count = int(run.config_json.get("star_count", pick_count))
        results = list(
            db.scalars(
                select(TicketResult).where(TicketResult.evaluation_run_id == evaluation.id)
            )
        )
        _add_performance_results(weekly_buckets[week], results, pick_count)
        _add_performance_results(overall, results, pick_count)
        period = period_buckets.setdefault(
            actual_draw.draw_no,
            {
                "draw_no": actual_draw.draw_no,
                "draw_date": actual_draw.draw_date.isoformat(),
                "stats": _empty_performance_bucket(),
                "comparison": _comparison_payload(
                    run,
                    actual_draw,
                    ruleset,
                    game,
                ),
            },
        )
        _add_performance_results(period["stats"], results, pick_count)

    weekly: list[dict[str, Any]] = []
    for week in sorted(weekly_buckets, reverse=True)[:10]:
        weekly.append(
            {
                "week": week,
                **_performance_rates(weekly_buckets[week]),
            }
        )
    recent_periods: list[dict[str, Any]] = []
    sorted_periods = sorted(
        period_buckets.values(),
        key=lambda item: (str(item["draw_date"]), str(item["draw_no"])),
        reverse=True,
    )
    recent_10 = _empty_performance_bucket()
    for period in sorted_periods[:10]:
        stats = period["stats"]
        _merge_performance(recent_10, stats)
        recent_periods.append(
            {
                "draw_no": period["draw_no"],
                "draw_date": period["draw_date"],
                **period["comparison"],
                **_performance_rates(stats),
            }
        )
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
        "source": "LOCKED_RECOMMENDATION_EVALUATION",
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
        .limit(8)
    )
    if official_count:
        runs_statement = runs_statement.where(Draw.source_status == "official")
    runs = list(db.scalars(runs_statement))
    records: list[dict[str, Any]] = []
    for run in runs:
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
            and latest is not None
            and record["cutoff_draw_no"] == latest.draw_no
        ),
        None,
    )
    primary_pick = int(ruleset.config_json["pools"][0]["pick_count"])
    wheel_modes = [
        size
        for size in (7, 8, 9)
        if game.game_type in {"unordered_unique_numbers", "derived_game"}
        and size > primary_pick
        and math.comb(size, primary_pick) <= 100
    ]
    performance = _performance_payload(db, game)
    return {
        "game": {
            "game_code": game.game_code,
            "display_name": game.display_name_zh_tw,
            "game_type": game.game_type,
            "primary_pick_count": primary_pick,
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
        "performance_source": performance.get("source"),
        "performance_replay_run_uuid": performance.get("replay_run_uuid"),
        "metric_note": (
            "週更以影片五步法逐期回放計算，每一期只使用該期以前資料。"
            "命中率＝已核對單式中至少命中1個主要號碼的比例；"
            "號碼正確率＝命中主要號碼總數除以核對號碼總數。"
            "近10期、最新一週與累計數字都是歷史紀錄，不是未來中獎機率。"
        ),
    }
