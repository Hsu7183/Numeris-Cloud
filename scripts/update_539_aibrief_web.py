"""Fetch Pilio AI brief ball mentions for the local website, preserving valid data."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import truststore
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://www.pilio.idv.tw/lto539/sqlaibrief.asp"
DATA = ROOT / "docs/data/539-aibrief.json"
STATUS = ROOT / "docs/data/539-aibrief-status.json"


def parse(content: str) -> dict:
    soup = BeautifulSoup(content, "html.parser")
    article = soup.select_one(".ai-brief")
    date_match = re.search(r"開獎更新日期\s*[:：]\s*(\d{4}/\d{2}/\d{2})", soup.get_text())
    if article is None or date_match is None:
        raise ValueError("來源格式改變，保留上次資料")
    text = article.get_text(" ", strip=True)
    if len(text) < 100:
        raise ValueError("文章不完整，保留上次資料")
    ball = r"(?:0?[1-9]|[12]\d|3[0-9])"
    sequence = rf"{ball}(?:\s*[,，、與及和]\s*{ball})*"
    patterns = [rf"(?<![\d.])({sequence})\s*(?:等)?號", rf"號碼\s*({sequence})(?![\d.])"]
    numbers = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            numbers.update(int(n) for n in re.findall(r"\d+", match.group(1)))
    if not numbers or not all(1 <= n <= 39 for n in numbers):
        raise ValueError("無法辨識有效球號，保留上次資料")
    date = datetime.strptime(date_match.group(1), "%Y/%m/%d").date()
    if date > datetime.now(ZoneInfo("Asia/Taipei")).date():
        raise ValueError("來源日期超出今天，保留上次資料")
    return dict(
        source_url=SOURCE,
        source_draw_date=date.isoformat(),
        mentioned_numbers=sorted(numbers),
        article_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def save_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    try:
        with httpx.Client(
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=45, follow_redirects=True
        ) as client:
            response = client.get(SOURCE)
            response.raise_for_status()
        payload = parse(response.content.decode("utf-8-sig"))
        old = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else None
        if old and old["source_draw_date"] > payload["source_draw_date"]:
            raise ValueError("來源日期較舊，保留上次資料")
        changed = not old or old.get("article_sha256") != payload["article_sha256"]
        payload["checked_at"] = now
        save_atomic(DATA, payload)
        save_atomic(STATUS, dict(ok=True, checked_at=now))
        print(json.dumps(dict(changed=changed, **payload), ensure_ascii=False))
    except Exception:
        save_atomic(STATUS, dict(ok=False, checked_at=now, message="來源更新失敗，保留上次資料"))
        raise


if __name__ == "__main__":
    main()
