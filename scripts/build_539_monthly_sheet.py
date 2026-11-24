"""Continuous A4 draw tables with twenty writing cells at the end."""
import argparse
import calendar
import json
import os
from datetime import date, timedelta
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]


def make_sheet(months, end_month, draws, output, publish=False):
    year, month = map(int, end_month.split('-'))
    end_index = year * 12 + month - 1
    selected = [divmod(i, 12) for i in range(end_index - months + 1, end_index + 1)]
    selected = [(y, m + 1) for y, m in selected]
    lookup = {row['draw_date']: row for row in draws}
    cutoff = max(lookup)
    start = date(*selected[0], 1)
    if start.isoformat() < min(lookup):
        raise ValueError('Source history does not cover requested months')
    end = date(year, month, calendar.monthrange(year, month)[1])
    included = sorted([row for row in draws if start.isoformat() <= row['draw_date'] <= end.isoformat()], key=lambda row: row['draw_date'])
    # The starting day can move so all three columns end on the same line.
    trim = (len(included) + 20) % 3
    if trim:
        included = included[trim:]
    displayed_start = date.fromisoformat(included[0]['draw_date'])
    expected = {d.isoformat() for y, m in selected for day in range(1, calendar.monthrange(y, m)[1] + 1)
                if (d := date(y, m, day)).isoformat() <= cutoff and d.weekday() != 6}
    if expected - lookup.keys():
        raise ValueError('Missing scheduled draw dates: ' + str(sorted(expected - lookup.keys())))
    fonts = [os.environ.get('NUMERIS_REPORT_FONT', ''), 'C:/Windows/Fonts/msjh.ttc', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']
    font = next((f for f in fonts if f and Path(f).is_file()), None)
    if not font:
        raise RuntimeError('Install a CJK font or set NUMERIS_REPORT_FONT')
    pdfmetrics.registerFont(TTFont('CJK', font, subfontIndex=0))
    output.mkdir(parents=True, exist_ok=True)
    path = output / ('latest.pdf' if publish else f'539-{months}months-{end_month}-v6.pdf')
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.setTitle(f'今彩539｜{months}個月開獎號碼與手寫空白格｜{end_month}')

    def text(x, top, value, size=8, center=False):
        c.setFont('CJK', size)
        (c.drawCentredString if center else c.drawString)(x, height - top, str(value))

    text(20, 28, f'今彩539｜{months}個月開獎號碼表', 16)
    text(20, 46, f'{displayed_start:%Y/%m/%d}–{cutoff.replace("-","/")}　共 {len(included)} 期', 8.5)
    text(20, 61, '由左欄往右欄接續；只列開獎日。月份只在每月第一筆標示。', 7.4)
    included = sorted(included, key=lambda row: row['draw_date'])
    margin, gap = 20, 7
    panel_width = (width - 2 * margin - 2 * gap) / 3
    # Fixed row capacity; historical data fills all but the last 20 rows.
    rows_per_column = (len(included) + 20) // 3
    data_top = 94
    row_height = (height - 132) / rows_per_column
    number_size = 10 if months == 3 else 9.45
    month_starts = {min(row['draw_date'] for row in included if row['draw_date'][:7] == ym)
                    for ym in {row['draw_date'][:7] for row in included}}
    c.setLineWidth(.45)
    for column in range(3):
        x = margin + column * (panel_width + gap)
        records = included[column * rows_per_column:(column + 1) * rows_per_column]
        if not records:
            continue
        col_widths = [32, 18] + [(panel_width - 50) / 5] * 5
        boundaries = [x]
        for cell_width in col_widths:
            boundaries.append(boundaries[-1] + cell_width)
        bottom = data_top + len(records) * row_height
        c.rect(x, height - bottom, panel_width, bottom - 76)
        c.line(x, height - data_top, x + panel_width, height - data_top)
        for row_index in range(1, len(records)):
            yy = data_top + row_index * row_height
            # A slightly heavier divider marks a new month within the column.
            c.setLineWidth(.8 if records[row_index]['draw_date'] in month_starts else .4)
            c.line(x, height - yy, x + panel_width, height - yy)
        c.setLineWidth(.45)
        for boundary in boundaries[1:3]:
            c.line(boundary, height - 76, boundary, height - bottom)
        for boundary in boundaries[3:7]:
            c.line(boundary, height - data_top, boundary, height - bottom)
        text((boundaries[0] + boundaries[1]) / 2, 88, '日期', 7.5, True)
        text((boundaries[1] + boundaries[2]) / 2, 88, '星期', 7, True)
        text((boundaries[2] + boundaries[7]) / 2, 88, '開出獎號（5碼）', 7.5, True)
        for index, record in enumerate(records):
            day_date = date.fromisoformat(record['draw_date'])
            baseline = data_top + (index + .5) * row_height + number_size * .34
            label = f'{day_date.month}/{day_date.day:02}' if record['draw_date'] in month_starts else f'{day_date.day:02}'
            text((boundaries[0] + boundaries[1]) / 2, baseline, label, 8 if '/' in label else 7, True)
            text((boundaries[1] + boundaries[2]) / 2, baseline, '一二三四五六日'[day_date.weekday()], 8, True)
            for i, number in enumerate(sorted(record['numbers'])):
                text((boundaries[i + 2] + boundaries[i + 3]) / 2, baseline, f'{number:02}', number_size, True)
        if column == 2:
            # Continue twenty future draw dates, each with five blank number cells.
            blank_top = bottom
            blank_x = boundaries[0]
            blank_width = boundaries[7] - blank_x
            c.rect(blank_x, height - blank_top - 20 * row_height, blank_width, 20 * row_height)
            for bx in boundaries[1:7]:
                c.line(bx, height - blank_top, bx, height - blank_top - 20 * row_height)
            for i in range(1, 20):
                yy = blank_top + i * row_height
                c.line(blank_x, height - yy, boundaries[7], height - yy)
            next_date = date.fromisoformat(records[-1]['draw_date'])
            for index in range(20):
                next_date += timedelta(days=1)
                while next_date.weekday() == 6:
                    next_date += timedelta(days=1)
                baseline = blank_top + (index + .5) * row_height + number_size * .34
                label = f'{next_date.month}/{next_date.day:02}' if next_date.day == 1 or (next_date.day == 2 and next_date.weekday() == 0) else f'{next_date.day:02}'
                text((boundaries[0] + boundaries[1]) / 2, baseline, label, 8 if '/' in label else 7, True)
                text((boundaries[1] + boundaries[2]) / 2, baseline, '一二三四五六日'[next_date.weekday()], 8, True)
    text(20, height - 18, '資料：台灣彩券官方歷史開獎資料｜A4直式・列印選「實際大小／100%」', 7)
    c.showPage()
    c.save()
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    assert abs(float(reader.pages[0].mediabox.width) - width) < .1
    document = pdfium.PdfDocument(str(path))
    document[0].render(scale=2).to_pil().save(path.with_suffix('.png'))
    document.close()
    path.with_suffix('.json').write_text(json.dumps(dict(months=months, start_date=displayed_start.isoformat(),
        end_date=end.isoformat(), cutoff=cutoff, draw_count=len(included), blank_draw_rows=20, writing_cells_at_end=100, number_font_pt=number_size,
        draws=sorted(included, key=lambda row: row['draw_date'])), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{path}: {len(included)} draws, one A4 page')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--end-month')
    parser.add_argument('--months', type=int, choices=(3,6), nargs='+', default=[3,6])
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    payload = json.loads((ROOT / 'docs/data/539-workbench.json').read_text(encoding='utf-8-sig'))
    end_month = args.end_month or max(row['draw_date'] for row in payload['draws'])[:7]
    for count in args.months:
        output = ROOT / f'docs/reports/539-{count}-months' if args.publish else ROOT / 'output/pdf/539-monthly'
        make_sheet(count, end_month, payload['draws'], output, args.publish)
