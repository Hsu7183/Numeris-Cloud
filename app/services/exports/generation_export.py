from __future__ import annotations

import csv
import io
import json
from typing import Any

from sqlalchemy.orm import Session

from app.services.generation.service import serialize_generation_run


def _flat_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticket in payload["tickets"]:
        pools = ticket["pools"]
        structure = ticket["explanation"]["structure"]
        temperatures = ticket["explanation"].get("temperature_counts", {})
        pool_codes = list(pools)
        rows.append(
            {
                "run_uuid": payload["run_uuid"],
                "game_code": payload["game_code"],
                "target_draw_no": payload["target_draw_no"],
                "cutoff_draw_no": payload["cutoff_draw_no"],
                "preset_code": payload["preset_code"],
                "random_seed": payload["random_seed"],
                "ticket_index": ticket["ticket_index"],
                "pool_1_numbers": " ".join(f"{number:02d}" for number in pools[pool_codes[0]]),
                "pool_2_numbers": (
                    " ".join(f"{number:02d}" for number in pools[pool_codes[1]])
                    if len(pool_codes) > 1
                    else ""
                ),
                "hot_count": temperatures.get("熱", 0),
                "warm_count": temperatures.get("溫", 0),
                "cold_count": temperatures.get("冷", 0),
                "odd_count": structure.get("odd_count"),
                "high_count": structure.get("high_count"),
                "sum": structure.get("sum"),
                "span": structure.get("span"),
                "ac": structure.get("ac"),
                "last_draw_overlap": structure.get("last_draw_overlap"),
                "preference_score": ticket["preference_score"],
                "diversity_score": ticket["diversity_score"],
                "locked": payload["locked"],
                "generated_at": payload["generated_at"],
            }
        )
    return rows


def export_csv(db: Session, run_uuid: str) -> bytes:
    payload = serialize_generation_run(db, run_uuid)
    rows = _flat_rows(payload)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]) if rows else [])
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def export_json(db: Session, run_uuid: str) -> bytes:
    payload = serialize_generation_run(db, run_uuid)
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def export_txt(db: Session, run_uuid: str) -> bytes:
    payload = serialize_generation_run(db, run_uuid)
    lines = [
        "Numeris 彩球分析與選號系統",
        f"彩種：{payload['game_name']}",
        f"目標期別：{payload['target_draw_no']}",
        f"資料截止：{payload['cutoff_draw_no']}",
        f"random seed：{payload['random_seed']}",
        "",
    ]
    for ticket in payload["tickets"]:
        pools = " + ".join(
            " ".join(f"{number:02d}" for number in numbers) for numbers in ticket["pools"].values()
        )
        lines.append(f"第{ticket['ticket_index']}組：{pools}")
        lines.append(ticket["explanation"]["message"])
    lines.extend(
        [
            "",
            "偏好分數只代表組合符合目前設定條件的程度，不代表實際開獎機率。",
            "歷史開獎結果不代表未來結果，產生的號碼不構成中獎保證。",
        ]
    )
    return ("\ufeff" + "\r\n".join(lines)).encode("utf-8")
