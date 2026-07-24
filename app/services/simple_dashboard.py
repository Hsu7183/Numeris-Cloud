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


def _weekly_performance(db: Session, game: Game) -> list[dict[str, Any]]:
    evaluations = list(
        db.scalars(
            select(EvaluationRun)
            .join(GenerationRun, EvaluationRun.generation_run_id == GenerationRun.id)
            .where(GenerationRun.game_id == game.id)
            .order_by(EvaluationRun.evaluated_at.desc())
            .limit(500)
        )
    )
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "evaluated_runs": 0,
            "tickets": 0,
            "tickets_with_hit": 0,
            "exact_tickets": 0,
            "hit_numbers": 0,
            "checked_numbers": 0,
            "best_hit": 0,
        }
    )
    for evaluation in evaluations:
        run = db.get(GenerationRun, evaluation.generation_run_id)
        if run is None:
            continue
        actual_draw = db.get(Draw, evaluation.actual_draw_id)
        if actual_draw is None or actual_draw.draw_no != run.target_draw_no:
            continue
        evaluated_at = evaluation.evaluated_at
        if evaluated_at.tzinfo is None:
            evaluated_at = evaluated_at.replace(tzinfo=UTC)
        iso = evaluated_at.astimezone(ZoneInfo("Asia/Taipei")).isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        bucket = buckets[week]
        bucket["evaluated_runs"] += 1
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
        bucket["tickets"] += len(results)
        bucket["checked_numbers"] += len(results) * pick_count
        for result in results:
            hits = int(result.main_hit_count)
            bucket["hit_numbers"] += hits
            bucket["best_hit"] = max(int(bucket["best_hit"]), hits)
            if hits > 0:
                bucket["tickets_with_hit"] += 1
            if hits >= pick_count:
                bucket["exact_tickets"] += 1
    output: list[dict[str, Any]] = []
    for week in sorted(buckets, reverse=True)[:8]:
        bucket = buckets[week]
        tickets = int(bucket["tickets"])
        checked_numbers = int(bucket["checked_numbers"])
        output.append(
            {
                "week": week,
                **bucket,
                "ticket_hit_rate": round(
                    int(bucket["tickets_with_hit"]) / tickets * 100, 2
                )
                if tickets
                else 0.0,
                "number_accuracy": round(
                    int(bucket["hit_numbers"]) / checked_numbers * 100, 2
                )
                if checked_numbers
                else 0.0,
            }
        )
    return output


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
        "weekly_performance": _weekly_performance(db, game),
        "metric_note": (
            "週命中率＝已核對單式中至少命中1個主要號碼的比例；"
            "號碼正確率＝命中主要號碼總數除以核對號碼總數。"
            "兩者都是歷史紀錄，不是未來中獎機率。"
        ),
    }
