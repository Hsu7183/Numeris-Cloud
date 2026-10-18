"""Fetch Lotto brief mentions separately from the Daily 539 brief."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import truststore
from bs4 import BeautifulSoup

from scripts.lotto649_modes import ROOT
from scripts.update_539_aibrief_web import save_atomic

SOURCE = "https://www.pilio.idv.tw/ltobig/sqlaibrief.asp"
DATA = ROOT / "docs/data/649-aibrief.json"
STATUS = ROOT / "docs/data/649-aibrief-status.json"


def parse(content):
    soup = BeautifulSoup(content, "html.parser")
    article = soup.select_one(".ai-brief")
    date_match = re.search(r"開獎更新日期\s*[:：]\s*(\d{4}/\d{2}/\d{2})", soup.get_text())
    if article is None or date_match is None:
        raise ValueError("大樂透AI快報格式改變")
    text = article.get_text(" ", strip=True)
    if len(text) < 100:
        raise ValueError("大樂透AI快報內容不足")
    ball = r"(?:0?[1-9]|[1-4]\d)"
    sequence = rf"{ball}(?:\s*[,，、與及和或]\s*{ball})*"
    numbers = sorted(
        {
            int(n)
            for match in re.finditer(rf"(?<![\d.])({sequence})\s*號", text)
            for n in re.findall(r"\d+", match.group(1))
        }
    )
    if not numbers:
        raise ValueError("未辨識到大樂透球號")
    date = datetime.strptime(date_match.group(1), "%Y/%m/%d").date()
    if date > datetime.now(ZoneInfo("Asia/Taipei")).date():
        raise ValueError("來源日期超出今天")
    # Only explicitly named balls are included; prose probabilities are never scores.
    return dict(
        source_url=SOURCE,
        source_draw_date=date.isoformat(),
        mentioned_numbers=numbers,
        article_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def main():
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
        payload["checked_at"] = now
        save_atomic(DATA, payload)
        save_atomic(STATUS, dict(ok=True, checked_at=now))
        print(json.dumps(payload, ensure_ascii=False))
    except Exception:
        save_atomic(
            STATUS, dict(ok=False, checked_at=now, message="大樂透快報更新失敗，保留上次有效資料")
        )
        raise


if __name__ == "__main__":
    main()
