"""Calculate report summaries using the same rendered grid as the website."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import os
from playwright.sync_api import sync_playwright


def calculate_blank_summaries(root):
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
                page.goto(f'http://127.0.0.1:{server.server_port}/handwritten-539-overlay.html', wait_until='domcontentloaded')
                page.wait_for_function("/已更新至|載入失敗/.test(document.querySelector('#overlay-status').textContent)", timeout=120000)
                status = page.locator('#overlay-status').inner_text()
                if not status.startswith('已更新至'):
                    raise RuntimeError(status)
                return page.locator('#blank-difference-panels .overlay-panel').evaluate_all("""panels => panels.map(panel => ({
                    long: Number(panel.dataset.blankLong), short: Number(panel.dataset.blankShort),
                    groups: [...panel.querySelectorAll('tbody tr')].map(row => ({
                        count: Number(row.querySelector('th').textContent),
                        numbers: [...row.querySelectorAll('td.blank-changed .comparison-ball')].map(ball => Number(ball.textContent))
                    })).filter(group => group.numbers.length)
                })).filter(panel => panel.groups.length)""")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
