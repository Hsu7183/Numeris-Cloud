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


def test_simple_recommendation_ui_flow() -> None:
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
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(base_url)
            page.get_by_role("heading", name="選一個彩種， 直接看下期組合。").wait_for()
            page.locator("#game-select").select_option("TW_LOTTO649")
            page.locator("#result-title").filter(has_text="大樂透").wait_for(timeout=30000)
            page.locator(".ticket").first.wait_for(state="visible")
            assert page.locator(".ticket").count() == 10
            assert "/api/exports/generation/" in (
                page.locator("#export-csv").get_attribute("href") or ""
            )

            page.locator("#game-select").select_option("HK_MARKSIX")
            page.locator("[data-mode='wheel7']").wait_for(state="visible")
            page.locator("[data-mode='wheel7']").click()
            page.locator("#generate").click()
            page.locator("#wheel-core").wait_for(state="visible", timeout=30000)
            assert page.locator(".ticket").count() == 7
            assert page.locator(".sidebar").count() == 0
            page.set_viewport_size({"width": 1920, "height": 1080})
            intro_layout = page.locator(".intro").evaluate(
                "element => getComputedStyle(element).display"
            )
            title_box = page.locator(".intro h1").bounding_box()
            picker_box = page.locator(".game-picker").bounding_box()
            assert intro_layout == "grid"
            assert title_box is not None and picker_box is not None
            assert picker_box["x"] > title_box["x"]
            assert not page_errors
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=15)
