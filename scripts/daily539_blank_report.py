"""Calculate report summaries using the same rendered grid as the website."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import os
import json
from playwright.sync_api import sync_playwright


def calculate_blank_summaries(root, include_ai=False, game="539"):
    if game not in ("539", "649"):
        raise ValueError("Unsupported report game")
    folder = "lotto649/" if game == "649" else ""
    ball_count = 49 if game == "649" else 39
    overlay = folder + f"handwritten-{game}-overlay"
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(root / 'docs')))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as runtime:
            options = {'headless': True, 'args': ['--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows']}
            edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
            if os.name == 'nt' and edge.exists():
                options['executable_path'] = str(edge)
            browser = runtime.chromium.launch(**options)
            try:
                page = browser.new_page(viewport={'width': 1500, 'height': 1200})
                # The report loads 48 historical iframe grids. Limit concurrency
                # in this headless session to avoid starving their ready timers.
                def report_overlay(route):
                    source = (root / ('docs/' + overlay + '.js')).read_text(encoding='utf-8')
                    source = source.replace('start += 6', 'start += 2').replace('start + 6', 'start + 2')
                    source = source.replace('}, 30000);', '}, 60000);')
                    route.fulfill(status=200, content_type='application/javascript; charset=utf-8', body=source)
                page.route(f'**/handwritten-{game}-overlay.js*', report_overlay)
                page.goto(f'http://127.0.0.1:{server.server_port}/{overlay}.html', wait_until='domcontentloaded')
                page.wait_for_function("/已更新至|載入失敗/.test(document.querySelector('#overlay-status').textContent)", timeout=120000)
                status = page.locator('#overlay-status').inner_text()
                if not status.startswith('已更新至'):
                    raise RuntimeError(status)
                summaries = page.locator('#blank-difference-panels .overlay-panel').evaluate_all("""panels => panels.map(panel => ({
                    long: Number(panel.dataset.blankLong), short: Number(panel.dataset.blankShort),
                    groups: [...panel.querySelectorAll('tbody tr')].map(row => ({
                        count: Number(row.querySelector('th').textContent),
                        numbers: [...row.querySelectorAll('td.blank-changed .comparison-ball')].map(ball => Number(ball.textContent))
                    })).filter(group => group.numbers.length)
                })).filter(panel => panel.groups.length)""")
                if not include_ai:
                    return summaries
                brief = json.loads((root / f'docs/data/{game}-aibrief.json').read_text(encoding='utf-8'))
                mentioned = brief['mentioned_numbers']
                if not all(type(n) is int and 1 <= n <= ball_count for n in mentioned):
                    raise ValueError('Invalid AI brief ball numbers')
                groups = page.locator('#adjacent-table tbody tr').evaluate_all("""rows => rows.map(row => ({
                    count: Number(row.querySelector('th').textContent),
                    numbers: [...row.querySelectorAll('td span')].map(ball => Number(ball.textContent))
                }))""")
                for group in groups:
                    group['numbers'] = [n for n in group['numbers'] if n in mentioned]
                return {'blank_summaries': summaries, 'ai_brief': {
                    'source_draw_date': brief['source_draw_date'], 'groups': groups}}
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
