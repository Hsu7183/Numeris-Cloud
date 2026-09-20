from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import logging
import ssl
import time
import uuid
import zipfile
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import truststore
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.database import SessionLocal
from app.core.paths import CONFIG_DIR, RAW_DIR
from app.models.database_models import Job, SourceArtifact
from app.services.bootstrap import load_json_yaml
from app.services.importers.draw_importer import (
    bulk_import_rows,
    summary_dict,
)

LOGGER = logging.getLogger("data_update")
USER_AGENT = "Numeris/1.0 (+local historical lottery data manager)"


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _get(url: str) -> httpx.Response:
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"},
        verify=ssl_context,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _post_json(url: str, payload: dict[str, Any]) -> httpx.Response:
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-TW,zh;q=0.9",
            "Origin": "https://bet.hkjc.com",
            "Referer": "https://bet.hkjc.com/",
        },
        verify=ssl_context,
    ) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response


TAIWAN_CSV_SCHEMAS: dict[str, dict[str, Any]] = {
    "大樂透": {
        "game_code": "TW_LOTTO649",
        "pool_code": "main",
        "number_count": 6,
        "special_column": "特別號",
    },
    "威力彩": {
        "game_code": "TW_SUPER_LOTTO638",
        "pool_code": "first",
        "number_count": 6,
        "second_pool_column": "第二區",
    },
    "今彩539": {
        "game_code": "TW_DAILY539",
        "pool_code": "main",
        "number_count": 5,
    },
    "3星彩": {
        "game_code": "TW_PICK3",
        "pool_code": "digits",
        "number_count": 3,
        "draw_order_known": True,
    },
    "4星彩": {
        "game_code": "TW_PICK4",
        "pool_code": "digits",
        "number_count": 4,
        "draw_order_known": True,
    },
    "賓果賓果": {
        "game_code": "TW_BINGO",
        "pool_code": "main",
        "number_count": 20,
    },
}


def _parse_taiwan_annual_zip(content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """解析台灣彩券年度 ZIP；只接受已明確驗證欄位的遊戲檔案。"""
    rows: list[dict[str, Any]] = []
    skipped_files: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for member in archive.infolist():
            filename = Path(member.filename).name
            if member.file_size > 100_000_000:
                raise ValueError(f"官方CSV超過安全大小限制：{filename}")
            with archive.open(member) as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                first_record = next(reader, None)
                game_name = (
                    str(first_record.get("遊戲名稱", "")).strip()
                    if first_record is not None
                    else ""
                )
                schema = TAIWAN_CSV_SCHEMAS.get(game_name)
                if schema is None:
                    skipped_files.append(filename)
                    continue
                required = {
                    "遊戲名稱",
                    "期別",
                    "開獎日期",
                    *(f"獎號{index}" for index in range(1, int(schema["number_count"]) + 1)),
                }
                if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                    missing = sorted(required - set(reader.fieldnames or []))
                    raise ValueError(f"官方CSV欄位不符：{filename}，缺少 {missing}")
                for record in itertools.chain([first_record], reader):
                    numbers = [
                        int(record[f"獎號{index}"])
                        for index in range(1, int(schema["number_count"]) + 1)
                    ]
                    parsed: dict[str, Any] = {
                        "market_code": "TW",
                        "game_code": schema["game_code"],
                        "draw_no": str(record["期別"]).strip(),
                        "draw_date": str(record["開獎日期"]).strip(),
                        "pool_code": schema["pool_code"],
                        "numbers": numbers,
                        "draw_order_known": bool(schema.get("draw_order_known", False)),
                        "source_reference": "台灣彩券官方年度開獎結果檔",
                    }
                    special_column = schema.get("special_column")
                    if special_column:
                        parsed["special_number"] = int(record[str(special_column)])
                    second_pool_column = schema.get("second_pool_column")
                    if second_pool_column:
                        parsed["second_pool_numbers"] = [int(record[str(second_pool_column)])]
                    rows.append(parsed)
    if not rows:
        raise ValueError("官方年度ZIP內沒有可安全解析的開獎資料")
    return rows, skipped_files


def create_update_job(db: Session, scope: str) -> dict[str, str]:
    if scope not in {"all", "taiwan", "hongkong", "reconcile"}:
        scope = "all"
    job_uuid = str(uuid.uuid4())
    db.add(
        Job(
            job_uuid=job_uuid,
            job_type="data_update",
            status="pending",
            progress_current=0,
            progress_total=2 if scope == "all" else 1,
            message="等待更新官方資料",
            parameters_json={"scope": scope},
        )
    )
    db.commit()
    return {"job_uuid": job_uuid, "status": "pending"}


def run_update_job(job_uuid: str) -> None:
    db = SessionLocal()
    job = db.scalar(select(Job).where(Job.job_uuid == job_uuid))
    if job is None:
        db.close()
        return
    try:
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.message = "正在連線官方資料來源"
        db.commit()
        scope = str(job.parameters_json.get("scope", "all"))
        results: dict[str, object] = {}
        steps = []
        if scope in {"all", "taiwan", "reconcile"}:
            steps.append(("taiwan", _update_taiwan))
        if scope in {"all", "hongkong", "reconcile"}:
            steps.append(("hongkong", _update_hong_kong))
        for index, (name, handler) in enumerate(steps, 1):
            db.refresh(job)
            if job.status == "cancelled":
                return
            try:
                results[name] = handler(db)
            except Exception as exc:
                LOGGER.exception("%s官方來源更新失敗", name)
                results[name] = {
                    "error": str(exc),
                    "parsed_draws": 0,
                    "notice": "此官方來源未取得資料；未編造或填補任何開獎資料。",
                }
            job.progress_current = index
            job.message = f"已完成 {index}/{len(steps)} 個官方來源檢查"
            db.commit()
        job.message = "官方資料完成，正在檢查近10週回測定錨"
        db.commit()
        try:
            from scripts.rebuild_weekly import main as rebuild_weekly
            from scripts.rebuild_weekly import needs_rebuild

            if needs_rebuild():
                rebuild_weekly()
                results["weekly_review"] = {
                    "status": "completed",
                    "message": "近10週回測定錨已隨最新開獎資料更新",
                }
            else:
                results["weekly_review"] = {
                    "status": "current",
                    "message": "近10週回測定錨已是最新",
                }
        except Exception as exc:
            LOGGER.exception("近10週回測定錨更新失敗")
            results["weekly_review"] = {
                "status": "failed",
                "error": str(exc),
                "message": "官方獎號已更新，但近10週回測整理失敗，可稍後重試",
            }
        job.status = "completed"
        job.message = "官方來源與近10週定錨檢查完成"
        job.result_json = results
        job.completed_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        LOGGER.exception("官方資料更新失敗")
        db.rollback()
        job = db.scalar(select(Job).where(Job.job_uuid == job_uuid))
        if job:
            job.status = "failed"
            job.message = f"官方資料更新失敗：{exc}"
            job.result_json = {
                "error": str(exc),
                "notice": "未編造或填補任何開獎資料，請使用手動匯入範本。",
            }
            job.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


def _save_artifact(
    db: Session,
    market: str,
    source_name: str,
    url: str,
    response: httpx.Response,
    destination: Path,
    parse_status: str,
) -> SourceArtifact:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    sha256 = hashlib.sha256(response.content).hexdigest()
    artifact = SourceArtifact(
        market_code=market,
        source_name=source_name,
        source_locator=url,
        local_path=str(destination),
        http_status=response.status_code,
        content_type=response.headers.get("content-type"),
        file_size=len(response.content),
        sha256=sha256,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        parser_version="1.2.0",
        parse_status=parse_status,
        validation_status="pending",
        error_message=None,
    )
    db.add(artifact)
    db.flush()
    return artifact


def _update_taiwan(db: Session) -> dict[str, object]:
    sources = load_json_yaml(CONFIG_DIR / "sources.yaml")["taiwan"]
    page_url = sources["annual_download_page"]
    response = _get(page_url)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    _save_artifact(
        db,
        "TW",
        "台灣彩券年度檔下載頁",
        page_url,
        response,
        RAW_DIR / "taiwan" / f"result_download_{stamp}.html",
        "discovered",
    )
    api_url = str(sources["annual_download_api"])
    allowed_hosts = set(sources["official_domains"])
    downloaded: list[dict[str, object]] = []
    parsed_draws = 0
    skipped_files: list[str] = []
    start_year = datetime.now().year
    first_year = int(sources.get("annual_first_year", start_year))
    years = range(start_year, first_year - 1, -1)
    for year in years:
        query_url = f"{api_url}?{urlencode({'year': year})}"
        known = db.scalar(
            select(SourceArtifact).where(
                SourceArtifact.source_locator
                == f"https://cdn.taiwanlottery.com.tw/app/FilesForDownload/Download/LottoResult/{year}.zip",
                SourceArtifact.validation_status == "verified",
            )
        )
        if known is not None and year < start_year:
            downloaded.append(
                {
                    "year": year,
                    "url": known.source_locator,
                    "path": known.local_path,
                    "sha256": known.sha256,
                    "import": {"processed": 0, "inserted": 0, "skipped": 0},
                    "cached": True,
                }
            )
            continue
        time.sleep(float(sources.get("request_interval_seconds", 1.5)))
        api_response = _get(query_url)
        _save_artifact(
            db,
            "TW",
            "台灣彩券年度檔官方API回應",
            query_url,
            api_response,
            RAW_DIR / "taiwan" / stamp / f"result_download_{year}.json",
            "discovered",
        )
        payload = api_response.json()
        content = payload.get("content") if isinstance(payload, dict) else None
        link = content.get("path") if isinstance(content, dict) else None
        if not isinstance(link, str) or not link:
            raise ValueError(f"官方年度檔API未回傳下載路徑：{year}")
        parsed_link = urlparse(link)
        if parsed_link.scheme != "https" or parsed_link.hostname not in allowed_hosts:
            raise ValueError(f"官方API回傳非允許網域：{parsed_link.hostname}")
        if Path(parsed_link.path).suffix.lower() != ".zip":
            raise ValueError(f"官方API回傳非ZIP檔案：{link}")
        time.sleep(float(sources.get("request_interval_seconds", 1.5)))
        file_response = _get(link)
        filename = Path(parsed_link.path).name or f"official_{year}.zip"
        destination = RAW_DIR / "taiwan" / stamp / filename
        artifact = _save_artifact(
            db,
            "TW",
            "台灣彩券官方年度檔",
            link,
            file_response,
            destination,
            "downloaded",
        )
        db.commit()
        annual_rows, annual_skipped = _parse_taiwan_annual_zip(file_response.content)
        summary = bulk_import_rows(
            db,
            annual_rows,
            source_name="台灣彩券官方年度檔",
            source_locator=link,
            local_path=str(destination),
            raw_sha256=artifact.sha256,
            official=True,
            source_artifact=artifact,
        )
        parsed_draws += summary.inserted
        skipped_files.extend(annual_skipped)
        downloaded.append(
            {
                "year": year,
                "url": link,
                "path": str(destination),
                "sha256": artifact.sha256,
                "import": summary_dict(summary),
            }
        )
    current = _update_taiwan_current(db, sources, stamp)
    parsed_draws += int(current["parsed_draws"])
    return {
        "discovery_page": str(response.url),
        "download_api": api_url,
        "download_links_found": len(downloaded),
        "downloaded": downloaded,
        "parsed_draws": parsed_draws,
        "current_month": current,
        "skipped_files": skipped_files,
        "notice": (
            "已透過官方API發現年度檔並完成欄位驗證；"
            "39／49樂合彩共用母遊戲開獎事件，加開獎項不作一般開獎匯入。"
        ),
    }


def _update_hong_kong(db: Session) -> dict[str, object]:
    sources = load_json_yaml(CONFIG_DIR / "sources.yaml")["hong_kong"]
    page_url = sources["results_page"]
    response = _get(page_url)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = RAW_DIR / "hong_kong" / f"marksix_results_{stamp}.html"
    _save_artifact(
        db,
        "HK",
        "香港賽馬會六合彩結果頁",
        page_url,
        response,
        destination,
        "endpoint_research_required",
    )
    db.commit()
    endpoint = str(sources["graphql_endpoint"])
    first_year = int(sources.get("history_first_year", 1993))
    today = date.today()
    ranges = list(_quarter_ranges(date(first_year, 1, 1), today))
    downloaded: list[dict[str, object]] = []
    parsed_draws = 0
    for start, end in ranges:
        logical_locator = (
            f"{endpoint}?startDate={start:%Y%m%d}&endDate={end:%Y%m%d}&drawType=All"
        )
        known = db.scalar(
            select(SourceArtifact).where(
                SourceArtifact.source_locator == logical_locator,
                SourceArtifact.validation_status == "verified",
            )
        )
        if known is not None and end < date(today.year, 1, 1):
            downloaded.append(
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "path": known.local_path,
                    "sha256": known.sha256,
                    "cached": True,
                }
            )
            continue
        time.sleep(float(sources.get("request_interval_seconds", 2.0)))
        api_response = _post_json(
            endpoint,
            {
                "query": HK_MARKSIX_QUERY,
                "variables": {
                    "startDate": start.strftime("%Y%m%d"),
                    "endDate": end.strftime("%Y%m%d"),
                    "drawType": "All",
                },
            },
        )
        api_payload = api_response.json()
        if api_payload.get("errors"):
            raise ValueError(
                f"香港賽馬會官方結果端點錯誤：{api_payload['errors']}"
            )
        api_destination = (
            RAW_DIR
            / "hong_kong"
            / stamp
            / f"marksix_{start:%Y%m%d}_{end:%Y%m%d}.json"
        )
        artifact = _save_artifact(
            db,
            "HK",
            "香港賽馬會六合彩官方GraphQL",
            logical_locator,
            api_response,
            api_destination,
            "downloaded",
        )
        db.commit()
        rows = _parse_hkjc_draws(api_payload)
        summary = bulk_import_rows(
            db,
            rows,
            source_name="香港賽馬會六合彩官方GraphQL",
            source_locator=logical_locator,
            local_path=str(api_destination),
            raw_sha256=artifact.sha256,
            official=True,
            source_artifact=artifact,
        )
        parsed_draws += summary.inserted
        downloaded.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "path": str(api_destination),
                "sha256": artifact.sha256,
                "draws": len(rows),
                "import": summary_dict(summary),
            }
        )
    return {
        "page": str(response.url),
        "raw_path": str(destination),
        "graphql_endpoint": endpoint,
        "history_first_year": first_year,
        "ranges": len(ranges),
        "downloaded": downloaded,
        "parsed_draws": parsed_draws,
        "notice": "已依官方結果頁實際使用的GraphQL端點下載並驗證六合彩歷史獎號。",
    }


TAIWAN_CURRENT_SCHEMAS: tuple[dict[str, Any], ...] = (
    {
        "endpoint": "SuperLotto638Result",
        "result_key": "superLotto638Res",
        "game_code": "TW_SUPER_LOTTO638",
        "pool_code": "first",
        "number_count": 6,
        "second_pool": True,
    },
    {
        "endpoint": "Lotto649Result",
        "result_key": "lotto649Res",
        "game_code": "TW_LOTTO649",
        "pool_code": "main",
        "number_count": 6,
        "special": True,
    },
    {
        "endpoint": "Daily539Result",
        "result_key": "daily539Res",
        "game_code": "TW_DAILY539",
        "pool_code": "main",
        "number_count": 5,
    },
    {
        "endpoint": "3DResult",
        "result_key": "lotto3DRes",
        "game_code": "TW_PICK3",
        "pool_code": "digits",
        "number_count": 3,
        "ordered": True,
    },
    {
        "endpoint": "4DResult",
        "result_key": "lotto4DRes",
        "game_code": "TW_PICK4",
        "pool_code": "digits",
        "number_count": 4,
        "ordered": True,
    },
)


def _update_taiwan_current(
    db: Session,
    sources: dict[str, Any],
    stamp: str,
) -> dict[str, object]:
    base_url = str(sources["current_results_api"]).rstrip("/")
    current_month = date.today().strftime("%Y-%m")
    results: list[dict[str, object]] = []
    parsed_draws = 0
    for schema in TAIWAN_CURRENT_SCHEMAS:
        query_url = (
            f"{base_url}/{schema['endpoint']}?"
            + urlencode(
                {
                    "month": current_month,
                    "endMonth": current_month,
                    "pageNum": 1,
                    "pageSize": 500,
                }
            )
        )
        time.sleep(float(sources.get("request_interval_seconds", 1.5)))
        response = _get(query_url)
        destination = (
            RAW_DIR
            / "taiwan"
            / stamp
            / f"current_{schema['endpoint']}_{current_month}.json"
        )
        artifact = _save_artifact(
            db,
            "TW",
            "台灣彩券當月官方查詢API",
            query_url,
            response,
            destination,
            "downloaded",
        )
        db.commit()
        content = response.json().get("content") or {}
        records = content.get(schema["result_key"]) or []
        rows: list[dict[str, Any]] = []
        for record in records:
            shown = [int(value) for value in record["drawNumberAppear"]]
            number_count = int(schema["number_count"])
            row: dict[str, Any] = {
                "market_code": "TW",
                "game_code": schema["game_code"],
                "draw_no": str(record["period"]),
                "draw_date": str(record["lotteryDate"]).split("T", 1)[0],
                "pool_code": schema["pool_code"],
                "numbers": shown[:number_count],
                "draw_order_known": bool(schema.get("ordered", False)),
                "source_reference": "台灣彩券當月官方查詢API",
            }
            if schema.get("special"):
                row["special_number"] = shown[number_count]
            if schema.get("second_pool"):
                row["second_pool_numbers"] = [shown[number_count]]
            rows.append(row)
        summary = bulk_import_rows(
            db,
            rows,
            source_name="台灣彩券當月官方查詢API",
            source_locator=query_url,
            local_path=str(destination),
            raw_sha256=artifact.sha256,
            official=True,
            source_artifact=artifact,
        )
        parsed_draws += summary.inserted
        results.append(
            {
                "game_code": schema["game_code"],
                "url": query_url,
                "path": str(destination),
                "sha256": artifact.sha256,
                "draws": len(rows),
                "import": summary_dict(summary),
            }
        )

    bingo_results: dict[str, object] = {
        "status": "disabled",
        "reason": "BINGO商品已停用",
        "parsed_draws": 0,
    }
    return {
        "month": current_month,
        "traditional": results,
        "bingo": bingo_results,
        "parsed_draws": parsed_draws,
    }


def _update_taiwan_current_bingo(
    db: Session,
    sources: dict[str, Any],
    stamp: str,
    base_url: str,
) -> dict[str, object]:
    today = date.today()
    current = today.replace(day=1)
    downloaded: list[dict[str, object]] = []
    parsed_draws = 0
    while current <= today:
        page = 1
        total = 1
        imported_for_day = 0
        while (page - 1) * 200 < total:
            query_url = (
                f"{base_url}/BingoResult?"
                + urlencode(
                    {
                        "openDate": current.isoformat(),
                        "pageNum": page,
                        "pageSize": 200,
                    }
                )
            )
            time.sleep(float(sources.get("request_interval_seconds", 1.5)))
            response = _get(query_url)
            payload = response.json().get("content") or {}
            total = int(payload.get("totalSize") or 0)
            records = payload.get("bingoQueryResult") or []
            destination = (
                RAW_DIR
                / "taiwan"
                / stamp
                / f"current_BingoResult_{current:%Y%m%d}_p{page}.json"
            )
            artifact = _save_artifact(
                db,
                "TW",
                "台灣彩券BINGO當日官方查詢API",
                query_url,
                response,
                destination,
                "downloaded",
            )
            db.commit()
            rows = [
                {
                    "market_code": "TW",
                    "game_code": "TW_BINGO",
                    "draw_no": str(record["drawTerm"]),
                    "draw_date": current.isoformat(),
                    "pool_code": "main",
                    "numbers": [int(value) for value in record["openShowOrder"]],
                    "draw_order_known": True,
                    "source_reference": "台灣彩券BINGO當日官方查詢API",
                }
                for record in records
            ]
            summary = bulk_import_rows(
                db,
                rows,
                source_name="台灣彩券BINGO當日官方查詢API",
                source_locator=query_url,
                local_path=str(destination),
                raw_sha256=artifact.sha256,
                official=True,
                source_artifact=artifact,
            )
            parsed_draws += summary.inserted
            imported_for_day += summary.inserted
            page += 1
            if not records:
                break
        downloaded.append(
            {
                "date": current.isoformat(),
                "official_total": total,
                "inserted": imported_for_day,
            }
        )
        current += timedelta(days=1)
    return {
        "days": len(downloaded),
        "downloaded": downloaded,
        "parsed_draws": parsed_draws,
    }


HK_MARKSIX_QUERY = """fragment lotteryDrawsFragment on LotteryDraw {
    id
    year
    no
    openDate
    closeDate
    drawDate
    status
    snowballCode
    snowballName_en
    snowballName_ch
    lotteryPool {
      sell
      status
      totalInvestment
      jackpot
      unitBet
      estimatedPrize
      derivedFirstPrizeDiv
      lotteryPrizes {
        type
        winningUnit
        dividend
      }
    }
    drawResult {
      drawnNo
      xDrawnNo
    }
  }
query marksixResult(
  $lastNDraw: Int,
  $startDate: String,
  $endDate: String,
  $drawType: LotteryDrawType
) {
            lotteryDraws(
              lastNDraw: $lastNDraw,
              startDate: $startDate,
              endDate: $endDate,
              drawType: $drawType
            ) {
              ...lotteryDrawsFragment
            }
        }"""


def _quarter_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    current = start
    while current <= end:
        quarter_end_month = ((current.month - 1) // 3 + 1) * 3
        quarter_end = date(
            current.year,
            quarter_end_month,
            monthrange(current.year, quarter_end_month)[1],
        )
        ranges.append((current, min(quarter_end, end)))
        current = quarter_end + timedelta(days=1)
    return ranges


def _parse_hkjc_draws(payload: dict[str, Any]) -> list[dict[str, Any]]:
    draws = (payload.get("data") or {}).get("lotteryDraws") or []
    rows: list[dict[str, Any]] = []
    for draw in draws:
        result = draw.get("drawResult") or {}
        numbers = [int(value) for value in result.get("drawnNo") or []]
        special = result.get("xDrawnNo")
        if draw.get("status") != "Result" or len(numbers) != 6 or special is None:
            continue
        rows.append(
            {
                "market_code": "HK",
                "game_code": "HK_MARKSIX",
                "draw_no": f"{str(draw['year'])[-2:]}/{int(draw['no']):03d}",
                "draw_date": str(draw["drawDate"]).split("+", 1)[0],
                "pool_code": "main",
                "numbers": numbers,
                "special_number": int(special),
                "source_reference": "香港賽馬會六合彩官方GraphQL",
            }
        )
    return rows


def job_to_dict(job: Job) -> dict[str, object]:
    return {
        "job_uuid": job.job_uuid,
        "job_type": job.job_type,
        "status": job.status,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "message": job.message,
        "parameters": job.parameters_json,
        "result": job.result_json,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def source_status_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
