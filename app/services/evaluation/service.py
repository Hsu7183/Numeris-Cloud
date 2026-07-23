from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NumerisError
from app.models.database_models import (
    Draw,
    EvaluationRun,
    Game,
    GeneratedTicket,
    GenerationRun,
    Ruleset,
    TicketResult,
)


def evaluate_generation_run(
    db: Session, run_uuid: str, actual_draw_no: str | None = None
) -> dict[str, Any]:
    run = db.scalar(
        select(GenerationRun)
        .where(GenerationRun.run_uuid == run_uuid)
        .options(selectinload(GenerationRun.tickets).selectinload(GeneratedTicket.numbers))
    )
    if run is None:
        raise NumerisError("RUN_NOT_FOUND", "找不到推薦紀錄")
    game = db.get(Game, run.game_id)
    if game is None:
        raise NumerisError("GAME_NOT_FOUND", "找不到推薦紀錄所屬彩種")
    draw = db.scalar(
        select(Draw)
        .where(
            Draw.game_id == game.id,
            Draw.draw_no == (actual_draw_no or run.target_draw_no),
        )
        .options(selectinload(Draw.numbers))
    )
    if draw is None:
        raise NumerisError(
            "DRAW_NOT_FOUND",
            "尚未找到目標期開獎資料",
            {"target_draw_no": actual_draw_no or run.target_draw_no},
        )
    ruleset = db.get(Ruleset, draw.ruleset_id)
    evaluation = EvaluationRun(
        generation_run_id=run.id,
        actual_draw_id=draw.id,
        ruleset_id=draw.ruleset_id,
        status="completed",
    )
    db.add(evaluation)
    db.flush()
    actual_by_pool: dict[str, list[int]] = defaultdict(list)
    special: int | None = None
    for number in draw.numbers:
        if number.is_special:
            special = number.number_value
        else:
            actual_by_pool[number.pool_code].append(number.number_value)

    results: list[dict[str, Any]] = []
    for ticket in run.tickets:
        ticket_by_pool: dict[str, list[int]] = defaultdict(list)
        for number in ticket.numbers:
            ticket_by_pool[number.pool_code].append(number.number_value)
        pool_results: dict[str, Any] = {}
        main_hit_count = 0
        if game.game_type == "ordered_digits":
            ticket_digits = next(iter(ticket_by_pool.values()))
            actual_digits = next(iter(actual_by_pool.values()))
            same_positions = sum(
                left == right
                for left, right in zip(ticket_digits, actual_digits, strict=False)
            )
            main_hit_count = same_positions
            pool_results["digits"] = {
                "same_position_count": same_positions,
                "exact_match": ticket_digits == actual_digits,
            }
        else:
            for pool_code, ticket_numbers in ticket_by_pool.items():
                hits = sorted(set(ticket_numbers) & set(actual_by_pool.get(pool_code, [])))
                pool_results[pool_code] = {
                    "hit_count": len(hits),
                    "hit_numbers": hits,
                }
                if pool_code in {"main", "first"}:
                    main_hit_count = len(hits)
        special_hit = special is not None and any(
            special in ticket_numbers for ticket_numbers in ticket_by_pool.values()
        )
        result_json = {
            "message": (
                "已完成號碼命中核對；獎等或獎金資料尚未驗證。"
                if not ruleset or not ruleset.verified
                else "已完成號碼命中核對；本期未載入完整官方獎金資料。"
            )
        }
        db.add(
            TicketResult(
                evaluation_run_id=evaluation.id,
                ticket_id=ticket.id,
                main_hit_count=main_hit_count,
                special_hit=special_hit,
                pool_results_json=pool_results,
                prize_tier_code=None,
                payout=None,
                payout_verified=False,
                result_json=result_json,
            )
        )
        results.append(
            {
                "ticket_index": ticket.ticket_index,
                "main_hit_count": main_hit_count,
                "special_hit": special_hit,
                "pool_results": pool_results,
                **result_json,
            }
        )
    db.commit()
    return {
        "run_uuid": run_uuid,
        "game_code": game.game_code,
        "actual_draw_no": draw.draw_no,
        "actual_draw_date": draw.draw_date.isoformat(),
        "results": results,
    }


def get_evaluation(db: Session, run_uuid: str) -> dict[str, Any]:
    run = db.scalar(select(GenerationRun).where(GenerationRun.run_uuid == run_uuid))
    if run is None:
        raise NumerisError("RUN_NOT_FOUND", "找不到推薦紀錄")
    evaluation = db.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.generation_run_id == run.id)
        .order_by(EvaluationRun.id.desc())
    )
    if evaluation is None:
        return {"run_uuid": run_uuid, "status": "尚未核對", "results": []}
    draw = db.get(Draw, evaluation.actual_draw_id)
    results = list(
        db.scalars(
            select(TicketResult)
            .where(TicketResult.evaluation_run_id == evaluation.id)
            .order_by(TicketResult.id)
        )
    )
    return {
        "run_uuid": run_uuid,
        "status": evaluation.status,
        "actual_draw_no": draw.draw_no if draw else None,
        "results": [
            {
                "main_hit_count": result.main_hit_count,
                "special_hit": result.special_hit,
                "pool_results": result.pool_results_json,
                "message": result.result_json.get("message"),
            }
            for result in results
        ],
    }
