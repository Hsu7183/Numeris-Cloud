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


def test_five_step_ui_flow() -> None:
    port = _free_port()
    source_db = Path("data/database/numeris.sqlite3").resolve()
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
            page.goto(base_url)
            page.get_by_role("button", name="影片五步選號").click()
            page.locator("#wizard-game").select_option("TW_LOTTO649")
            page.locator("#wizard-next").click()
            page.locator("[data-step-panel='2']").wait_for(state="visible")
            page.locator("[data-step='5']").click()
            page.locator("#wizard-count").fill("10")
            page.locator("#wizard-seed").fill("24680")
            page.locator("#generate-button").click()
            page.locator(".ticket-card").first.wait_for(state="visible", timeout=30000)
            assert page.locator(".ticket-card").count() == 10
            page.locator("#lock-run").click()
            page.get_by_text("已鎖定", exact=True).wait_for(timeout=10000)
            page.get_by_role("button", name="推薦紀錄").click()
            page.locator(".record").first.wait_for(state="visible")
            assert page.locator(".record").count() >= 1
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=15)
