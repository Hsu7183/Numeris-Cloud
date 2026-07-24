from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    elif process.poll() is None:
        process.terminate()
        process.wait(timeout=15)


def test_simple_recommendation_ui_flow() -> None:
    port = _free_port()
    database_url = os.environ["NUMERIS_DATABASE_URL"]
    source_db = Path(database_url.removeprefix("sqlite:///")).resolve()
    e2e_db = Path(f"data/cache/numeris_e2e_{port}.sqlite3").resolve()
    e2e_db.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(source_db)
    target_connection = sqlite3.connect(e2e_db)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    process_env = os.environ.copy()
    process_env["NUMERIS_DATABASE_URL"] = f"sqlite:///{e2e_db.as_posix()}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=process_env,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                if httpx.get(f"{base_url}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise AssertionError("測試伺服器未能啟動")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(base_url)
            page.get_by_role("heading", name="選擇商品／彩種").wait_for()
            page.get_by_text("近10期號碼命中率", exact=True).wait_for()
            page.get_by_text("累計號碼命中率", exact=True).wait_for()
            page.locator("#game-select").select_option("TW_LOTTO649")
            page.locator("#choice-title").filter(has_text="大樂透").wait_for(
                timeout=30000
            )
            page.locator("#open-combinations").wait_for(timeout=30000)
            page.locator("#open-combinations").click()
            page.locator("#result-title").filter(has_text="大樂透").wait_for()
            page.locator(".ticket").first.wait_for(state="visible")
            assert page.locator(".ticket").count() == 10
            assert "/api/exports/generation/" in (
                page.locator("#export-csv").get_attribute("href") or ""
            )

            page.locator("#close-combinations").click()
            page.locator("#game-select").select_option("HK_MARKSIX")
            page.locator("[data-mode='wheel7']").wait_for(state="visible")
            page.locator("[data-mode='wheel7']").click()
            page.locator("#generate").click()
            page.locator("#open-combinations").click()
            page.locator("#wheel-core").wait_for(state="visible", timeout=30000)
            assert page.locator(".ticket").count() == 7
            assert page.locator(".sidebar").count() == 0
            page.set_viewport_size({"width": 1920, "height": 1080})
            desktop_metrics = page.evaluate(
                """() => ({
                    clientWidth: document.documentElement.clientWidth,
                    clientHeight: document.documentElement.clientHeight,
                    scrollWidth: document.documentElement.scrollWidth,
                    scrollHeight: document.documentElement.scrollHeight,
                })"""
            )
            choice_box = page.locator(".choice-card").bounding_box()
            summary_box = page.locator(".summary-card").bounding_box()
            performance_box = page.locator(".performance-section").bounding_box()
            summary_ball_box = page.locator(".summary-ball").first.bounding_box()
            metric_font_size = page.locator(".performance-cards strong").first.evaluate(
                "(element) => parseFloat(getComputedStyle(element).fontSize)"
            )
            assert desktop_metrics["scrollWidth"] == desktop_metrics["clientWidth"]
            assert desktop_metrics["scrollHeight"] == desktop_metrics["clientHeight"]
            assert choice_box is not None and summary_box is not None
            assert performance_box is not None
            assert summary_ball_box is not None and summary_ball_box["width"] >= 60
            assert metric_font_size >= 38
            assert choice_box["x"] < summary_box["x"]
            assert performance_box["y"] > summary_box["y"]

            page.set_viewport_size({"width": 1366, "height": 768})
            compact_metrics = page.evaluate(
                """() => ({
                    clientWidth: document.documentElement.clientWidth,
                    clientHeight: document.documentElement.clientHeight,
                    scrollWidth: document.documentElement.scrollWidth,
                    scrollHeight: document.documentElement.scrollHeight,
                })"""
            )
            assert compact_metrics["scrollWidth"] == compact_metrics["clientWidth"]
            assert compact_metrics["scrollHeight"] == compact_metrics["clientHeight"]
            assert page.locator(".ticket").count() == 6
            page.locator("#ticket-next").click()
            assert page.locator("#ticket-page").inner_text() == "第 2／2 頁"
            assert page.locator(".ticket").count() == 1
            assert not page_errors
            browser.close()
    finally:
        _stop_process_tree(process)
        for suffix in ("", "-wal", "-shm"):
            e2e_db.with_name(e2e_db.name + suffix).unlink(missing_ok=True)
