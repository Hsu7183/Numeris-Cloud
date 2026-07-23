from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import __version__
from app.core.exceptions import GenerationError
from app.models.api_models import GenerationRequest
from app.models.database_models import (
    AuditLog,
    Draw,
    Game,
    GeneratedTicket,
    GeneratedTicketNumber,
    GenerationPreset,
    GenerationRun,
    Ruleset,
)
from app.services.analytics.core import analyze_numbers, calculate_ac
from app.services.bootstrap import canonical_hash
from app.services.generation.generators import (
    BingoGenerator,
    Candidate,
    MultiPoolGenerator,
    OrderedDigitGenerator,
    UnorderedCombinationGenerator,
)


def get_game_and_ruleset(db: Session, game_code: str) -> tuple[Game, Ruleset]:
    game = db.scalar(select(Game).where(Game.game_code == game_code))
    if game is None:
        raise GenerationError("GAME_NOT_FOUND", "找不到指定彩種", {"game_code": game_code})
    ruleset = db.scalar(
        select(Ruleset)
        .where(Ruleset.game_id == game.id, Ruleset.status == "active")
        .order_by(Ruleset.id.desc())
    )
    if ruleset is None:
        raise GenerationError("RULESET_NOT_FOUND", "找不到有效彩種規則")
    return game, ruleset


def _draws_for_game(db: Session, game: Game, limit: int | None = None) -> list[Draw]:
    query_game = game
    if game.parent_game_code:
        parent = db.scalar(select(Game).where(Game.game_code == game.parent_game_code))
        if parent is not None:
            query_game = parent
    statement = (
        select(Draw)
        .where(Draw.game_id == query_game.id)
        .options(selectinload(Draw.numbers))
        .order_by(Draw.draw_date.desc(), Draw.draw_no.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(reversed(list(db.scalars(statement))))


def _pool_draws(draws: list[Draw], pool_code: str) -> tuple[list[list[int]], list[str]]:
    samples: list[list[int]] = []
    draw_nos: list[str] = []
    for draw in draws:
        numbers = [
            item.number_value
            for item in sorted(
                (
                    number
                    for number in draw.numbers
                    if number.pool_code == pool_code and not number.is_special
                ),
                key=lambda item: (
                    item.draw_order if item.draw_order is not None else 999,
                    item.sorted_order if item.sorted_order is not None else 999,
                ),
            )
        ]
        if numbers:
            samples.append(numbers)
            draw_nos.append(draw.draw_no)
    return samples, draw_nos


def analysis_for_game(db: Session, game_code: str, lookback_count: int = 20) -> dict[str, Any]:
    game, ruleset = get_game_and_ruleset(db, game_code)
    draws = _draws_for_game(db, game, lookback_count)
    if not draws:
        raise GenerationError("NO_DATA", "此彩種尚無可分析的開獎資料")
    selected = draws[-lookback_count:]
    pools: dict[str, Any] = {}
    for pool in ruleset.config_json["pools"]:
        samples, draw_nos = _pool_draws(selected, str(pool["code"]))
        if not samples:
            continue
        metrics = analyze_numbers(
            samples,
            int(pool["min"]),
            int(pool["max"]),
            int(pool["draw_count"]),
            draw_nos,
        )
        pools[str(pool["code"])] = {
            "label": pool["label"],
            "metrics": metrics,
            "actual_lookback": len(samples),
        }
    return {
        "game_code": game.game_code,
        "game_name": game.display_name_zh_tw,
        "cutoff_draw_no": draws[-1].draw_no,
        "cutoff_draw_date": draws[-1].draw_date.isoformat(),
        "requested_lookback": lookback_count,
        "actual_lookback": len(selected),
        "verification_status": draws[-1].verification_status,
        "ruleset_version": ruleset.version,
        "ruleset_verified": ruleset.verified,
        "pools": pools,
    }


def _historical_ac_range(
    draws: list[Draw], pool_code: str, pick_count: int
) -> tuple[int | None, int | None]:
    values: list[int] = []
    for draw in draws[-100:]:
        numbers = [
            item.number_value
            for item in draw.numbers
            if item.pool_code == pool_code and not item.is_special
        ]
        if len(numbers) == pick_count and len(set(numbers)) == pick_count and pick_count >= 3:
            values.append(calculate_ac(numbers))
    if not values:
        return None, None
    return int(np.percentile(values, 20, method="lower")), int(
        np.percentile(values, 80, method="higher")
    )


def _next_draw_no(latest: str) -> str:
    prefix = latest.rstrip("0123456789")
    suffix = latest[len(prefix) :]
    if suffix:
        return f"{prefix}{int(suffix) + 1:0{len(suffix)}d}"
    return f"NEXT-{latest}"


def create_generation_run(db: Session, request: GenerationRequest) -> dict[str, Any]:
    game, ruleset = get_game_and_ruleset(db, request.game_code)
    all_draws = _draws_for_game(db, game, max(request.lookback_count, 100))
    if not all_draws:
        raise GenerationError("NO_DATA", "此彩種尚無可用資料；請先匯入官方檔案或fixture")
    selected_draws = all_draws[-request.lookback_count :]
    primary_pool = dict(ruleset.config_json["pools"][0])
    if game.game_type == "high_frequency":
        primary_pool["pick_count"] = request.star_count

    metrics_by_pool: dict[str, list[dict[str, Any]]] = {}
    previous_by_pool: dict[str, list[int]] = {}
    for pool in ruleset.config_json["pools"]:
        pool_copy = dict(pool)
        samples, draw_nos = _pool_draws(selected_draws, str(pool["code"]))
        if not samples:
            continue
        metrics_by_pool[str(pool["code"])] = analyze_numbers(
            samples,
            int(pool_copy["min"]),
            int(pool_copy["max"]),
            int(pool_copy["draw_count"]),
            draw_nos,
        )
        previous_by_pool[str(pool["code"])] = samples[-1]

    preset = db.scalar(
        select(GenerationPreset).where(
            GenerationPreset.preset_code == request.preset_code,
            GenerationPreset.active.is_(True),
        )
    )
    if preset is None:
        raise GenerationError("PRESET_NOT_FOUND", "找不到指定選號模式")

    ac_min, ac_max = request.ac_min, request.ac_max
    if game.supports_ac and ac_min is None and ac_max is None:
        ac_min, ac_max = _historical_ac_range(
            all_draws, str(primary_pool["code"]), int(primary_pool["pick_count"])
        )

    generator_kwargs: dict[str, Any] = {
        "count": request.ticket_count,
        "include_numbers": request.include_numbers,
        "exclude_numbers": request.exclude_numbers,
        "allowed_odd_counts": request.allowed_odd_counts,
        "allowed_high_counts": request.allowed_high_counts,
        "ac_min": ac_min,
        "ac_max": ac_max,
        "max_overlap": request.max_overlap,
        "max_attempts": request.max_attempts,
    }
    if game.game_type == "multi_pool":
        generator = MultiPoolGenerator(request.random_seed)
        candidates, diagnostics = generator.generate(
            pools=ruleset.config_json["pools"],
            metrics_by_pool=metrics_by_pool,
            previous_by_pool=previous_by_pool,
            **generator_kwargs,
        )
    elif game.game_type == "ordered_digits":
        generator = OrderedDigitGenerator(request.random_seed)
        candidates, diagnostics = generator.generate(
            count=request.ticket_count,
            pool=primary_pool,
            previous_numbers=previous_by_pool.get(str(primary_pool["code"])),
            max_overlap=request.max_overlap,
        )
    elif game.game_type == "high_frequency":
        generator = BingoGenerator(request.random_seed)
        candidates, diagnostics = generator.generate(
            pool=primary_pool,
            metrics=metrics_by_pool[str(primary_pool["code"])],
            previous_numbers=previous_by_pool.get(str(primary_pool["code"])),
            **generator_kwargs,
        )
    else:
        generator = UnorderedCombinationGenerator(request.random_seed)
        candidates, diagnostics = generator.generate(
            pool=primary_pool,
            metrics=metrics_by_pool[str(primary_pool["code"])],
            previous_numbers=previous_by_pool.get(str(primary_pool["code"])),
            **generator_kwargs,
        )

    config = request.model_dump()
    config["effective_ac_min"] = ac_min
    config["effective_ac_max"] = ac_max
    config["actual_lookback"] = len(selected_draws)
    run = GenerationRun(
        run_uuid=str(uuid.uuid4()),
        game_id=game.id,
        target_draw_no=request.target_draw_no or _next_draw_no(all_draws[-1].draw_no),
        cutoff_draw_id=all_draws[-1].id,
        preset_id=preset.id,
        requested_ticket_count=request.ticket_count,
        generated_ticket_count=len(candidates),
        random_seed=request.random_seed,
        config_json=config,
        config_hash=canonical_hash(config),
        app_version=__version__,
        status="completed",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        diagnostic_json=diagnostics,
    )
    db.add(run)
    db.flush()
    _save_candidates(db, run, candidates, game.game_type == "ordered_digits")
    db.add(
        AuditLog(
            action="generation.created",
            entity_type="generation_run",
            entity_id=run.run_uuid,
            detail_json={"seed": request.random_seed, "ticket_count": len(candidates)},
        )
    )
    db.commit()
    return serialize_generation_run(db, run.run_uuid)


def _save_candidates(
    db: Session, run: GenerationRun, candidates: list[Candidate], ordered_digits: bool
) -> None:
    for ticket_index, candidate in enumerate(candidates, 1):
        ticket = GeneratedTicket(
            generation_run_id=run.id,
            ticket_index=ticket_index,
            preference_score=candidate.preference_score,
            diversity_score=candidate.diversity_score,
            explanation_json={
                **candidate.explanation,
                "structure": candidate.structure,
            },
            ticket_hash=candidate.ticket_hash,
        )
        db.add(ticket)
        db.flush()
        for pool_code, numbers in candidate.pools.items():
            for index, number in enumerate(numbers, 1):
                db.add(
                    GeneratedTicketNumber(
                        ticket_id=ticket.id,
                        pool_code=pool_code,
                        position_index=index if ordered_digits else None,
                        number_value=number,
                        display_order=index,
                    )
                )


def serialize_generation_run(db: Session, run_uuid: str) -> dict[str, Any]:
    run = db.scalar(
        select(GenerationRun)
        .where(GenerationRun.run_uuid == run_uuid)
        .options(selectinload(GenerationRun.tickets).selectinload(GeneratedTicket.numbers))
    )
    if run is None:
        raise GenerationError("RUN_NOT_FOUND", "找不到推薦紀錄", {"run_uuid": run_uuid})
    game = db.get(Game, run.game_id)
    cutoff = db.get(Draw, run.cutoff_draw_id)
    preset = db.get(GenerationPreset, run.preset_id)
    return {
        "run_uuid": run.run_uuid,
        "game_code": game.game_code if game else None,
        "game_name": game.display_name_zh_tw if game else None,
        "target_draw_no": run.target_draw_no,
        "cutoff_draw_no": cutoff.draw_no if cutoff else None,
        "cutoff_draw_date": cutoff.draw_date.isoformat() if cutoff else None,
        "preset_code": preset.preset_code if preset else None,
        "preset_name": preset.display_name if preset else None,
        "random_seed": run.random_seed,
        "requested_ticket_count": run.requested_ticket_count,
        "generated_ticket_count": run.generated_ticket_count,
        "locked": run.locked,
        "locked_at": run.locked_at.isoformat() if run.locked_at else None,
        "status": run.status,
        "config": run.config_json,
        "config_hash": run.config_hash,
        "diagnostics": run.diagnostic_json,
        "generated_at": run.completed_at.isoformat() if run.completed_at else None,
        "tickets": [
            {
                "ticket_index": ticket.ticket_index,
                "pools": {
                    pool_code: [
                        number.number_value
                        for number in ticket.numbers
                        if number.pool_code == pool_code
                    ]
                    for pool_code in dict.fromkeys(number.pool_code for number in ticket.numbers)
                },
                "preference_score": ticket.preference_score,
                "diversity_score": ticket.diversity_score,
                "explanation": ticket.explanation_json,
            }
            for ticket in run.tickets
        ],
    }


def list_generation_runs(db: Session, limit: int = 50) -> list[dict[str, Any]]:
    run_uuids = list(
        db.scalars(
            select(GenerationRun.run_uuid)
            .order_by(GenerationRun.id.desc())
            .limit(min(max(limit, 1), 200))
        )
    )
    return [serialize_generation_run(db, run_uuid) for run_uuid in run_uuids]


def lock_generation_run(db: Session, run_uuid: str) -> dict[str, Any]:
    run = db.scalar(select(GenerationRun).where(GenerationRun.run_uuid == run_uuid))
    if run is None:
        raise GenerationError("RUN_NOT_FOUND", "找不到推薦紀錄")
    if not run.locked:
        run.locked = True
        run.locked_at = datetime.now(UTC)
        db.add(
            AuditLog(
                action="generation.locked",
                entity_type="generation_run",
                entity_id=run_uuid,
                detail_json={"locked_at": run.locked_at.isoformat()},
            )
        )
        db.commit()
    return serialize_generation_run(db, run_uuid)


def reproducibility_payload(payload: dict[str, Any]) -> str:
    """測試與稽核用：忽略run UUID後，比對可重現的核心輸出。"""
    stable = {
        "game_code": payload["game_code"],
        "random_seed": payload["random_seed"],
        "config": payload["config"],
        "tickets": [
            {
                "pools": ticket["pools"],
                "preference_score": ticket["preference_score"],
                "diversity_score": ticket["diversity_score"],
            }
            for ticket in payload["tickets"]
        ],
    }
    return json.dumps(stable, ensure_ascii=False, sort_keys=True)
