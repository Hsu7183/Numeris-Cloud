"""Fetch dated Fantasy 5 results from the user's selected 速彩 source."""
import html
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCES = (
    'https://www.sc888.net/index.php?id=winningnum&s=/LotteryFan/index',
    'https://webthirdthrees.sc888.net/index.php?s=/LotteryFan/index',
)


def parse_draws(source):
    draws = {}
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', source, re.S | re.I):
        cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
        if len(cells) < 2:
            continue
        label = html.unescape(re.sub('<[^>]+>', ' ', cells[0]))
        match = re.search(r'(\d{4,8})\s*\D*?(\d{4}-\d{2}-\d{2})', label)
        if not match:
            continue
        numbers = [int(n) for n in re.findall(r'<strong\b[^>]*>\s*(\d{1,2})\s*</strong>', cells[1], re.I)]
        if len(numbers) != 5 or len(set(numbers)) != 5 or not all(1 <= n <= 39 for n in numbers):
            continue
        draw_date = date.fromisoformat(match[2]).isoformat()
        record = dict(draw_date=draw_date, draw_no=match[1], numbers=numbers)
        if draw_date in draws and draws[draw_date] != record:
            raise ValueError('Conflicting source rows')
        draws[draw_date] = record
    if not draws:
        raise ValueError('No valid dated draw rows')
    return draws


def refresh(root, report_date):
    path = Path(root) / 'docs/data/california-daily.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    draws = previous.get('draws', {})
    errors = []
    checked = datetime.now(ZoneInfo('Asia/Taipei')).isoformat()
    for url in SOURCES:
        try:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
            with urlopen(request, timeout=20) as response:
                fetched = parse_draws(response.read().decode('utf-8', errors='replace'))
            # Source dates are displayed as Taiwan dates; do not shift them again.
            draws.update({d: dict(v, source_url=url) for d, v in fetched.items() if d <= report_date})
            if report_date in fetched:
                break
        except Exception as exc:
            errors.append(type(exc).__name__)
    record = draws.get(report_date)
    result = dict(report_date=report_date, status='current' if record else 'pending',
                  draw=record, checked_at=checked, errors=errors, draws=draws)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
    return result
