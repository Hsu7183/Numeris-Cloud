"""Browser checks for the deployed static Pages flows (serve docs on port 8765)."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


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
