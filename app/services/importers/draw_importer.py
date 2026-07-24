from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.database_models import Draw, DrawNumber, Game, Ruleset, SourceArtifact
from app.services.bootstrap import load_json_yaml


@dataclass
class ImportSummary:
    processed: int = 0
    inserted: int = 0
    skipped: int = 0
    conflicts: int = 0
    errors: int = 0


def _normalize_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(str(value), errors="raise").date()
    except Exception as exc:
        raise ValidationError("IMPORT_DATE", "開獎日期無法解析", {"value": str(value)}) from exc


def _validate_numbers(
    config: dict[str, Any],
    pool_code: str,
    numbers: list[int],
    special_number: int | None,
) -> dict[str, Any]:
    pool = next((item for item in config["pools"] if item["code"] == pool_code), None)
    if pool is None:
        raise ValidationError("IMPORT_POOL", "號碼池代碼不符合遊戲規則", {"pool": pool_code})
    expected_count = int(pool["draw_count"])
    if len(numbers) != expected_count:
        raise ValidationError(
            "IMPORT_COUNT",
            "開獎號碼個數與規則不符",
            {"expected": expected_count, "actual": len(numbers)},
        )
    if any(number < int(pool["min"]) or number > int(pool["max"]) for number in numbers):
        raise ValidationError("IMPORT_RANGE", "開獎號碼超出合法範圍")
    if bool(pool["unique"]) and len(set(numbers)) != len(numbers):
        raise ValidationError("IMPORT_DUPLICATE", "同一號碼池內不得有重複號碼")
    if special_number is not None:
        if not config.get("supports_special_ball"):
            raise ValidationError("IMPORT_SPECIAL", "此遊戲沒有特別號")
        if special_number < int(pool["min"]) or special_number > int(pool["max"]):
            raise ValidationError("IMPORT_SPECIAL_RANGE", "特別號超出合法範圍")
        if special_number in numbers:
            raise ValidationError("IMPORT_SPECIAL_DUPLICATE", "特別號不得與主要號碼重複")
    return pool


def import_rows(
    db: Session,
    rows: list[dict[str, Any]],
    source_name: str,
    source_locator: str,
    local_path: str,
    raw_sha256: str | None = None,
    official: bool = False,
    source_artifact: SourceArtifact | None = None,
) -> ImportSummary:
    summary = ImportSummary()
    raw_sha256 = (
        raw_sha256
        or hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    )
    artifact = source_artifact
    if artifact is None:
        artifact = SourceArtifact(
            market_code=str(rows[0]["market_code"]) if rows else "UNKNOWN",
            source_name=source_name,
            source_locator=source_locator,
            local_path=local_path,
            http_status=None,
            content_type="application/json",
            file_size=len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")),
            sha256=raw_sha256,
            parser_version="1.0.0",
            parse_status="running",
            validation_status="pending",
        )
        db.add(artifact)
        db.flush()
    else:
        artifact.parse_status = "running"
        artifact.validation_status = "pending"
    try:
        for row in rows:
            summary.processed += 1
            game = db.scalar(select(Game).where(Game.game_code == str(row["game_code"])))
            if game is None:
                raise ValidationError(
                    "IMPORT_GAME", "找不到遊戲代碼", {"game_code": row["game_code"]}
                )
            ruleset = db.scalar(
                select(Ruleset)
                .where(Ruleset.game_id == game.id, Ruleset.status == "active")
                .order_by(Ruleset.id.desc())
            )
            if ruleset is None:
                raise ValidationError("IMPORT_RULESET", "找不到有效遊戲規則")
            pool_code = str(row.get("pool_code", "main"))
            numbers = [int(value) for value in row["numbers"]]
            special = row.get("special_number")
            special_number = int(special) if special not in (None, "", "nan") else None
            pool = _validate_numbers(ruleset.config_json, pool_code, numbers, special_number)
            draw_no = str(row["draw_no"]).strip()
            draw_date = _normalize_date(row["draw_date"])
            existing = db.scalar(
                select(Draw).where(Draw.game_id == game.id, Draw.draw_no == draw_no)
            )
            if existing:
                current = [
                    item.number_value
                    for item in existing.numbers
                    if item.pool_code == pool_code and not item.is_special
                ]
                current_special = next(
                    (
                        item.number_value
                        for item in existing.numbers
                        if item.pool_code == "special" and item.is_special
                    ),
                    None,
                )
                if current == numbers and current_special == special_number:
                    summary.skipped += 1
                    continue
                existing.verification_status = "conflict"
                summary.conflicts += 1
                continue
            draw = Draw(
                game_id=game.id,
                ruleset_id=ruleset.id,
                draw_no=draw_no,
                draw_date=draw_date,
                local_timezone="Asia/Taipei",
                source_artifact_id=artifact.id,
                source_status="official" if official else "fixture",
                verification_status="verified" if official else "fixture_verified",
            )
            db.add(draw)
            db.flush()
            ordered = bool(pool["ordered"])
            draw_order_known = bool(row.get("draw_order_known", ordered))
            sorted_positions = (
                {value: index + 1 for index, value in enumerate(sorted(numbers))}
                if bool(pool["unique"])
                else {}
            )
            for index, number in enumerate(numbers, 1):
                db.add(
                    DrawNumber(
                        draw_id=draw.id,
                        pool_code=pool_code,
                        draw_order=index if draw_order_known else None,
                        sorted_order=index if ordered else sorted_positions[number],
                        number_value=number,
                        is_special=False,
                    )
                )
            second_numbers = [int(value) for value in row.get("second_pool_numbers", [])]
            if second_numbers:
                second_pool = _validate_numbers(
                    ruleset.config_json,
                    str(ruleset.config_json["pools"][1]["code"]),
                    second_numbers,
                    None,
                )
                for index, number in enumerate(second_numbers, 1):
                    db.add(
                        DrawNumber(
                            draw_id=draw.id,
                            pool_code=str(second_pool["code"]),
                            draw_order=(
                                index
                                if bool(row.get("second_pool_draw_order_known", False))
                                else None
                            ),
                            sorted_order=index,
                            number_value=number,
                            is_special=False,
                        )
                    )
            if special_number is not None:
                db.add(
                    DrawNumber(
                        draw_id=draw.id,
                        pool_code="special",
                        draw_order=None,
                        sorted_order=None,
                        number_value=special_number,
                        is_special=True,
                    )
                )
            summary.inserted += 1
        artifact.parse_status = "completed"
        artifact.validation_status = (
            "conflict" if summary.conflicts else "verified" if official else "fixture_verified"
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise exc
    return summary


def bulk_import_rows(
    db: Session,
    rows: list[dict[str, Any]],
    source_name: str,
    source_locator: str,
    local_path: str,
    raw_sha256: str | None = None,
    official: bool = False,
    source_artifact: SourceArtifact | None = None,
    batch_size: int = 500,
) -> ImportSummary:
    """大量官方資料匯入。

    與 ``import_rows`` 使用相同驗證與衝突規則，但以批次查詢及批次寫入處理
    BINGO年度檔，避免每一期都個別查詢與 flush。
    """
    summary = ImportSummary()
    raw_sha256 = (
        raw_sha256
        or hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    )
    artifact = source_artifact
    if artifact is None:
        encoded = json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")
        artifact = SourceArtifact(
            market_code=str(rows[0]["market_code"]) if rows else "UNKNOWN",
            source_name=source_name,
            source_locator=source_locator,
            local_path=local_path,
            http_status=None,
            content_type="application/json",
            file_size=len(encoded),
            sha256=raw_sha256,
            parser_version="1.2.0",
            parse_status="running",
            validation_status="pending",
        )
        db.add(artifact)
        db.flush()
    else:
        artifact.parse_status = "running"
        artifact.validation_status = "pending"

    game_codes = sorted({str(row["game_code"]) for row in rows})
    games = {
        game.game_code: game
        for game in db.scalars(select(Game).where(Game.game_code.in_(game_codes)))
    }
    missing_games = sorted(set(game_codes) - set(games))
    if missing_games:
        raise ValidationError("IMPORT_GAME", "找不到遊戲代碼", {"game_codes": missing_games})
    rulesets: dict[int, Ruleset] = {}
    for game in games.values():
        ruleset = db.scalar(
            select(Ruleset)
            .where(Ruleset.game_id == game.id, Ruleset.status == "active")
            .order_by(Ruleset.id.desc())
        )
        if ruleset is None:
            raise ValidationError(
                "IMPORT_RULESET",
                "找不到有效遊戲規則",
                {"game_code": game.game_code},
            )
        rulesets[game.id] = ruleset

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["game_code"]), []).append(row)

    try:
        for game_code, game_rows in grouped.items():
            game = games[game_code]
            ruleset = rulesets[game.id]
            for offset in range(0, len(game_rows), batch_size):
                batch = game_rows[offset : offset + batch_size]
                draw_nos = [str(row["draw_no"]).strip() for row in batch]
                existing_rows = db.execute(
                    select(
                        Draw.id,
                        Draw.draw_no,
                        DrawNumber.pool_code,
                        DrawNumber.number_value,
                        DrawNumber.is_special,
                        DrawNumber.id,
                    )
                    .outerjoin(DrawNumber, DrawNumber.draw_id == Draw.id)
                    .where(Draw.game_id == game.id, Draw.draw_no.in_(draw_nos))
                    .order_by(Draw.id, DrawNumber.id)
                ).all()
                existing: dict[str, dict[str, Any]] = {}
                for (
                    draw_id,
                    draw_no,
                    pool_code,
                    number_value,
                    is_special,
                    _number_id,
                ) in existing_rows:
                    item = existing.setdefault(
                        str(draw_no),
                        {"id": int(draw_id), "numbers": []},
                    )
                    if number_value is not None:
                        item["numbers"].append(
                            (str(pool_code), int(number_value), bool(is_special))
                        )

                pending: list[dict[str, Any]] = []
                for row in batch:
                    summary.processed += 1
                    pool_code = str(row.get("pool_code", "main"))
                    numbers = [int(value) for value in row["numbers"]]
                    special = row.get("special_number")
                    special_number = (
                        int(special) if special not in (None, "", "nan") else None
                    )
                    pool = _validate_numbers(
                        ruleset.config_json,
                        pool_code,
                        numbers,
                        special_number,
                    )
                    second_numbers = [
                        int(value) for value in row.get("second_pool_numbers", [])
                    ]
                    second_pool: dict[str, Any] | None = None
                    if second_numbers:
                        second_pool = _validate_numbers(
                            ruleset.config_json,
                            str(ruleset.config_json["pools"][1]["code"]),
                            second_numbers,
                            None,
                        )
                    draw_no = str(row["draw_no"]).strip()
                    found = existing.get(draw_no)
                    if found is not None:
                        current = [
                            value
                            for code, value, is_special in found["numbers"]
                            if code == pool_code and not is_special
                        ]
                        current_special = next(
                            (
                                value
                                for _code, value, is_special in found["numbers"]
                                if is_special
                            ),
                            None,
                        )
                        if current == numbers and current_special == special_number:
                            summary.skipped += 1
                        else:
                            db.execute(
                                update(Draw)
                                .where(Draw.id == int(found["id"]))
                                .values(verification_status="conflict")
                            )
                            summary.conflicts += 1
                        continue
                    pending.append(
                        {
                            "row": row,
                            "draw_no": draw_no,
                            "draw_date": _normalize_date(row["draw_date"]),
                            "pool": pool,
                            "pool_code": pool_code,
                            "numbers": numbers,
                            "special_number": special_number,
                            "second_numbers": second_numbers,
                            "second_pool": second_pool,
                        }
                    )

                if not pending:
                    db.flush()
                    continue
                draw_values = [
                    {
                        "game_id": game.id,
                        "ruleset_id": ruleset.id,
                        "draw_no": item["draw_no"],
                        "draw_date": item["draw_date"],
                        "local_timezone": "Asia/Taipei",
                        "source_artifact_id": artifact.id,
                        "source_status": "official" if official else "fixture",
                        "verification_status": (
                            "verified" if official else "fixture_verified"
                        ),
                    }
                    for item in pending
                ]
                db.execute(insert(Draw), draw_values)
                inserted_draws = dict(
                    db.execute(
                        select(Draw.draw_no, Draw.id).where(
                            Draw.game_id == game.id,
                            Draw.draw_no.in_([item["draw_no"] for item in pending]),
                        )
                    ).all()
                )
                number_values: list[dict[str, Any]] = []
                for item in pending:
                    draw_id = int(inserted_draws[item["draw_no"]])
                    numbers = item["numbers"]
                    pool = item["pool"]
                    ordered = bool(pool["ordered"])
                    draw_order_known = bool(
                        item["row"].get("draw_order_known", ordered)
                    )
                    sorted_positions = (
                        {
                            value: index + 1
                            for index, value in enumerate(sorted(numbers))
                        }
                        if bool(pool["unique"])
                        else {}
                    )
                    for index, number in enumerate(numbers, 1):
                        number_values.append(
                            {
                                "draw_id": draw_id,
                                "pool_code": item["pool_code"],
                                "draw_order": index if draw_order_known else None,
                                "sorted_order": (
                                    index if ordered else sorted_positions[number]
                                ),
                                "number_value": number,
                                "is_special": False,
                            }
                        )
                    if item["second_numbers"]:
                        second_pool = item["second_pool"]
                        for index, number in enumerate(item["second_numbers"], 1):
                            number_values.append(
                                {
                                    "draw_id": draw_id,
                                    "pool_code": str(second_pool["code"]),
                                    "draw_order": (
                                        index
                                        if bool(
                                            item["row"].get(
                                                "second_pool_draw_order_known",
                                                False,
                                            )
                                        )
                                        else None
                                    ),
                                    "sorted_order": index,
                                    "number_value": number,
                                    "is_special": False,
                                }
                            )
                    if item["special_number"] is not None:
                        number_values.append(
                            {
                                "draw_id": draw_id,
                                "pool_code": "special",
                                "draw_order": None,
                                "sorted_order": None,
                                "number_value": item["special_number"],
                                "is_special": True,
                            }
                        )
                if number_values:
                    db.execute(insert(DrawNumber), number_values)
                summary.inserted += len(pending)
                db.flush()

        artifact.parser_version = "1.2.0"
        artifact.parse_status = "completed"
        artifact.validation_status = (
            "conflict" if summary.conflicts else "verified" if official else "fixture_verified"
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary


def _extract_rows_from_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    required = {"market_code", "game_code", "draw_no", "draw_date"}
    if not required.issubset(frame.columns):
        raise ValidationError(
            "IMPORT_COLUMNS",
            "匯入檔缺少必要欄位",
            {"missing": sorted(required - set(frame.columns))},
        )
    number_columns = sorted(
        [column for column in frame.columns if str(column).startswith("number_")],
        key=lambda column: int(str(column).split("_")[-1]),
    )
    if not number_columns:
        raise ValidationError("IMPORT_COLUMNS", "匯入檔沒有number_1等號碼欄位")
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        numbers = [int(record[column]) for column in number_columns if pd.notna(record.get(column))]
        rows.append(
            {
                "market_code": record["market_code"],
                "game_code": record["game_code"],
                "draw_no": str(record["draw_no"]),
                "draw_date": record["draw_date"],
                "pool_code": record.get("pool_code", "main"),
                "numbers": numbers,
                "special_number": record.get("special_number"),
                "source_reference": record.get("source_reference", "手動匯入"),
            }
        )
    return rows


def import_file(db: Session, path: Path) -> ImportSummary:
    content = path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path, dtype={"draw_no": str})
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, dtype={"draw_no": str})
    else:
        raise ValidationError("IMPORT_FORMAT", "僅支援CSV、XLSX與XLS檔案")
    rows = _extract_rows_from_frame(frame)
    return import_rows(
        db,
        rows,
        source_name="手動匯入",
        source_locator=str(path.name),
        local_path=str(path),
        raw_sha256=sha256,
        official=False,
    )


def generate_fixture_rows(draws_per_game: int = 60) -> list[dict[str, Any]]:
    """建立固定測試資料；所有資料都清楚標記為fixture，不冒充官方資料。"""
    configs = [
        load_json_yaml(path)
        for path in sorted(
            Path(__file__).resolve().parents[3].joinpath("config/games").glob("*.yaml")
        )
        if path.stem not in {"tw_39match", "tw_49match"}
    ]
    rows: list[dict[str, Any]] = []
    base_date = date(2024, 1, 1)
    for config_index, config in enumerate(configs):
        rng = np.random.Generator(np.random.PCG64(1000 + config_index))
        for draw_index in range(draws_per_game):
            draw_no = f"F{draw_index + 1:04d}"
            for pool in config["pools"]:
                if config["game_type"] == "multi_pool" and pool["code"] == "second":
                    continue
                if pool["unique"]:
                    numbers = sorted(
                        int(value)
                        for value in rng.choice(
                            np.arange(int(pool["min"]), int(pool["max"]) + 1),
                            size=int(pool["draw_count"]),
                            replace=False,
                        )
                    )
                else:
                    numbers = [
                        int(value)
                        for value in rng.integers(
                            int(pool["min"]), int(pool["max"]) + 1, size=int(pool["draw_count"])
                        )
                    ]
                special: int | None = None
                if config.get("supports_special_ball"):
                    choices = [
                        value
                        for value in range(int(pool["min"]), int(pool["max"]) + 1)
                        if value not in numbers
                    ]
                    special = int(rng.choice(choices))
                rows.append(
                    {
                        "market_code": config["market_code"],
                        "game_code": config["game_code"],
                        "draw_no": draw_no,
                        "draw_date": base_date + timedelta(days=draw_index),
                        "pool_code": pool["code"],
                        "numbers": numbers,
                        "special_number": special,
                        "source_reference": "Numeris固定測試fixture",
                    }
                )
            if config["game_type"] == "multi_pool":
                # 合併多號碼池到同一期；匯入服務由專用函式處理。
                first_row = rows[-1]
                first_row["second_pool_numbers"] = [
                    int(rng.integers(1, int(config["pools"][1]["max"]) + 1))
                ]
    return rows


def write_fixture_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    max_numbers = max(len(row["numbers"]) for row in rows)
    fieldnames = [
        "market_code",
        "game_code",
        "draw_no",
        "draw_date",
        "pool_code",
        *(f"number_{index}" for index in range(1, max_numbers + 1)),
        "special_number",
        "source_reference",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            record = {
                "market_code": row["market_code"],
                "game_code": row["game_code"],
                "draw_no": row["draw_no"],
                "draw_date": row["draw_date"].isoformat(),
                "pool_code": row["pool_code"],
                "special_number": row.get("special_number"),
                "source_reference": row["source_reference"],
            }
            for index, number in enumerate(row["numbers"], 1):
                record[f"number_{index}"] = number
            writer.writerow(record)


def summary_dict(summary: ImportSummary) -> dict[str, int]:
    return asdict(summary)
