"""Refresh official Lotto sources and rebuild the local daily A4 report."""
import json
import logging
from pathlib import Path
import subprocess
import sys
import truststore

ROOT = Path(__file__).resolve().parents[1]


def main():
    truststore.inject_into_ssl()
    from scripts.export_lotto649_static import export_payload, write_history
    payload = export_payload()
    history_path = ROOT / 'docs/data/649-history.json'
    history = json.loads(history_path.read_text(encoding='utf-8'))['draws']
    merged = {row['draw_no']: row for row in history}
    merged.update({row['draw_no']: row for row in payload['draws']})
    write_history(history_path, sorted(merged.values(), key=lambda r: (r['draw_date'], r['draw_no']), reverse=True))
    target = ROOT / 'docs/data/lotto649.json'
    pending = target.with_suffix('.tmp')
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    pending.replace(target)
    brief = subprocess.run([sys.executable, '-m', 'scripts.update_lotto649_aibrief'], cwd=ROOT)
    if brief.returncode:
        logging.warning('Lotto AI brief unavailable; retained the last valid dated source')
    subprocess.run([sys.executable, '-m', 'scripts.build_649_daily_report'], cwd=ROOT, check=True)
    print('Local Lotto 6/49 daily A4 report refreshed successfully')


if __name__ == '__main__':
    main()
