from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import ssl
import time
import uuid
import zipfile
from datetime import UTC, datetime
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
from app.services.importers.draw_importer import import_rows, summary_dict

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
            game_name = filename.rsplit("_", 1)[0]
            schema = TAIWAN_CSV_SCHEMAS.get(game_name)
            if schema is None:
                skipped_files.append(filename)
                continue
            if member.file_size > 100_000_000:
                raise ValueError(f"官方CSV超過安全大小限制：{filename}")
            with archive.open(member) as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                required = {
                    "遊戲名稱",
                    "期別",
                    "開獎日期",
                    *(f"獎號{index}" for index in range(1, int(schema["number_count"]) + 1)),
                }
                if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                    missing = sorted(required - set(reader.fieldnames or []))
                    raise ValueError(f"官方CSV欄位不符：{filename}，缺少 {missing}")
                for record in reader:
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
        job.status = "completed"
        job.message = "官方來源檢查完成"
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
        parser_version="1.0.0",
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
    years = range(start_year, start_year - int(sources.get("annual_years_back", 0)) - 1, -1)
    for year in years:
        query_url = f"{api_url}?{urlencode({'year': year})}"
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
        summary = import_rows(
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
    return {
        "discovery_page": str(response.url),
        "download_api": api_url,
        "download_links_found": len(downloaded),
        "downloaded": downloaded,
        "parsed_draws": parsed_draws,
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
    return {
        "page": str(response.url),
        "raw_path": str(destination),
        "parsed_draws": 0,
        "notice": (
            "已保存官方結果頁原始內容；尚未確認穩定官方JSON端點，"
            "因此未把HTML畫面文字當成正式開獎資料。"
        ),
    }


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
