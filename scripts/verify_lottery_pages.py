"""Browser checks for the deployed static Pages flows (serve docs on port 8765)."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def verify_overlay(page, base: str, folder: str, game: str, columns: int) -> None:
    data = page.request.get(base + "data/" + game + ".json").json()
    page.goto(
        base + folder + "handwritten-" + ("539" if game == "daily539" else "649") + "-overlay.html"
    )
    page.wait_for_function(
        "document.querySelector('#overlay-status').textContent.startsWith('已更新至')",
        timeout=60000,
    )
    panels = page.locator("#overlay-panels > .overlay-panel")
    assert panels.count() == 5
    previous = None
    for index, periods in enumerate([30, 24, 18, 12, 6]):
        panel = panels.nth(index)
        assert panel.locator("header strong").inner_text() == f"近 {periods} 期疊加"
        assert panel.locator("thead th").count() == columns + 1
        first_date = data["draws"][periods - 1]["draw_date"].replace("-", "/")
        assert first_date in panel.locator("header span").inner_text()
        counts = panel.locator("tbody td").evaluate_all(
            "cells => cells.map(cell => "
            "Number(cell.querySelector('.overlay-circle')?.textContent || 0))"
        )
        assert len(counts) == columns * 5
        assert all(0 <= count <= periods for count in counts)
        if previous is not None:
            assert all(short <= long for short, long in zip(counts, previous, strict=True))
        previous = counts
    assert page.locator("#blank-difference-panels > .overlay-panel").count() == 5
    assert page.locator(".blank-summary").first.get_attribute("colspan") == str(columns + 1)
    print("PASS", game, "6/12/18/24/30 periods and cumulative counts")


def verify_recent_grid(page, base: str, folder: str, game: str) -> None:
    data = page.request.get(base + "data/" + game + ".json").json()
    number = "539" if game == "daily539" else "649"
    page.goto(base + folder + f"handwritten-{number}-grid.html")
    dates = page.locator('#draw-date-nav a[href*="?date="]')
    dates.first.wait_for()
    assert dates.count() == 30
    assert dates.first.get_attribute("href").endswith(data["draws"][29]["draw_date"])
    assert dates.last.get_attribute("href").endswith(data["draws"][0]["draw_date"])
    dates.first.click()
    page.wait_for_function(
        "document.querySelector('#sheet-status').textContent.startsWith('指定期別')",
        timeout=30000,
    )
    assert data["draws"][29]["draw_no"] in page.locator("#sheet-status").inner_text()
    print("PASS", game, "30 recent dates and oldest draw selection")


def main() -> None:
    payload = json.loads((ROOT / "docs/data/lotto649.json").read_text(encoding="utf-8"))
    assert len(payload["draws"]) == 200
    assert all(len(draw["numbers"]) == 6 for draw in payload["draws"])
    assert all(
        len(set(draw["numbers"] + draw["special_numbers"])) == 7 for draw in payload["draws"]
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response",
            lambda response: errors.append(response.url) if response.status >= 400 else None,
        )
        base = "http://127.0.0.1:8765/"
        page.goto(base)
        assert page.locator(".games a").count() == 2
        page.locator(".daily").click()
        page.locator(".adjacent-summary-panel").wait_for()
        assert page.locator(".adjacent-summary-panel .ball").count() == 39
        verify_overlay(page, base, "", "daily539", 20)
        verify_recent_grid(page, base, "", "daily539")
        page.goto(base)
        page.locator(".lotto").click()
        page.locator(".adjacent-summary-panel").wait_for()
        assert page.locator(".adjacent-summary-panel .ball").count() == 49
        assert "特別號" in page.locator("#latest-draw").inner_text()
        assert page.evaluate("!!localStorage.getItem('daily539OutputData')")
        assert page.evaluate("!!localStorage.getItem('lotto649OutputData')")
        for name, selector in [
            ("output.html", "#matrix-wrap tbody tr"),
            ("period-grid.html", ".period-panel"),
            ("pattern-grid.html", ".pattern-board"),
            ("pattern-template.html", ".month-row"),
            ("excel-649-grid.html", ".number-board tbody tr"),
            ("handwritten-649-grid.html", "#draw-grid tbody tr"),
            ("handwritten-649-overlay.html", ".overlay-panel tbody tr"),
        ]:
            page.goto(base + "lotto649/" + name)
            page.locator(selector).first.wait_for(timeout=60000)
            if name == "output.html":
                assert page.locator("#matrix-wrap tbody tr").count() == 24
                assert page.locator("#matrix-wrap thead tr").last.locator("th").count() == 49
            if name == "pattern-grid.html":
                headers = page.locator(".upper-half thead th").all_text_contents()
                numbers = sorted(int(n) for n in headers if n.isdigit())
                assert numbers == list(range(1, 50))
            if name == "handwritten-649-grid.html":
                numbers = page.locator("#draw-grid td").all_text_contents()
                assert sorted(int(n) for n in numbers if n.strip()) == list(range(1, 50))
            if name == "handwritten-649-overlay.html":
                assert page.locator(".overlay-panel").first.locator("thead th").count() == 50
            print("PASS", name)
        verify_overlay(page, base, "lotto649/", "lotto649", 49)
        verify_recent_grid(page, base, "lotto649/", "lotto649")
        page.goto(base)
        page.screenshot(path=str(ROOT / "output/lottery-home.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator(".lotto").click()
        page.locator(".adjacent-summary-panel").wait_for()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        browser.close()
    print("PASS homepage, 539 regression, 49-ball layouts, data isolation and mobile")


if __name__ == "__main__":
    main()
