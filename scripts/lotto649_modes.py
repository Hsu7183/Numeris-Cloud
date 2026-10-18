"""Lotto counterparts of the 539 ranking, replay, combined and audit modes."""

# ruff: noqa: E501 -- standalone report HTML and CSS markup.
from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from scripts.backtest_539_adjacent import TOPS
from scripts.backtest_539_adjacent import rank as score_rank
from scripts.backtest_539_adjacent_counts import rank as count_rank

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/lotto649"
PERIODS = (6, 12, 18, 24, 30, 36, 42, 48)
STYLE = """body{font-family:"Microsoft JhengHei",sans-serif;margin:24px;background:#f5f7f2;color:#193e30}main{max-width:1500px;margin:auto;min-width:0}a{color:#076b50}nav{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}section{margin:20px 0}p{line-height:1.8}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;background:white}td,th{padding:9px;border:1px solid #ccd8ce;text-align:center;white-space:nowrap}th{background:#e4eddf}.ranking-strip{container-type:inline-size}.ranking-strip table{table-layout:fixed}.ranking-strip td{width:calc(100% / 49);padding:8px 0}.ranking-strip small,.ranking-strip b{display:block;font-size:clamp(1px,.9cqw,15px)}.ranking-strip b{margin-top:8px}.filters{display:flex;gap:10px;flex-wrap:wrap}label{display:grid;gap:5px}input,select,button{font:inherit;padding:8px}iframe{width:100%;height:1000px;border:1px solid #ccd8ce}.frequencies{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}.frequencies span{background:white;padding:8px;text-align:center}.frequencies b{display:block}@media(max-width:600px){body{margin:12px}h1{font-size:24px}}"""


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def page(name: str, title: str, body: str, script: str = ""):
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / name).write_text(
        f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>大樂透｜{title}</title><link rel="stylesheet" href="649-hit-ranking.css"><link rel="stylesheet" href="649-aibrief.css"><style>{STYLE}</style></head><body><main><nav aria-label="大樂透模式"><a href="index.html">← 大樂透首頁</a><a href="649-dashboard.html">完整總覽</a><a href="649-adjacent-reference.html">相鄰次數</a><a href="649-combined-reference.html">相鄰分數＋AI快報</a><a href="649-adjacent-backtest.html">分數歷史試算</a><a href="649-adjacent-counts-backtest.html">次數歷史試算</a><a href="handwritten-649-overlay.html">期數疊加</a></nav><h1>大樂透 · {title}</h1>{body}</main>{script}</body></html>',
        encoding="utf-8",
    )


def load_history():
    snapshot_path = ROOT / "reports/649-adjacent-source.json"
    snapshot = (
        json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else []
    )
    merged = {d["draw_no"]: d for d in snapshot}
    database = ROOT / "data/database/numeris.sqlite3"
    conflicts = set()
    if database.exists():
        with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
            rows = connection.execute("""SELECT d.draw_no,d.draw_date,d.verification_status,n.number_value,n.is_special
                FROM draws d JOIN games g ON g.id=d.game_id JOIN draw_numbers n ON n.draw_id=d.id
                WHERE g.game_code='TW_LOTTO649' AND d.source_status='official'
                ORDER BY d.draw_date,d.draw_no,n.number_value""").fetchall()
        database_draws = {}
        for number, date, state, ball, special in rows:
            if state == "conflict":
                conflicts.add(number)
            draw = database_draws.setdefault(
                number,
                dict(
                    draw_no=number,
                    draw_date=date,
                    numbers=[],
                    special_numbers=[],
                    source_status="official",
                ),
            )
            draw["special_numbers" if special else "numbers"].append(ball)
        merged.update(database_draws)
    payload = json.loads((ROOT / "docs/data/lotto649.json").read_text(encoding="utf-8"))
    for draw in payload["draws"]:
        if draw["source_status"] != "official":
            raise ValueError("大樂透近期資料包含非官方來源")
        merged[draw["draw_no"]] = draw
        conflicts.discard(draw["draw_no"])
    if conflicts:
        raise ValueError(f"大樂透尚有未解決的來源衝突：{sorted(conflicts)}")
    history = sorted(merged.values(), key=lambda d: (d["draw_date"], d["draw_no"]))
    if len(history) <= 200:
        raise ValueError("大樂透歷史試算至少需要201期；請保留歷史快照")
    assert len(history) >= len(snapshot)
    assert len({d["draw_date"] for d in history}) == len(history)
    for draw in history:
        assert len(set(draw["numbers"])) == len(draw["numbers"]) == 6
        assert all(1 <= n <= 49 for n in draw["numbers"])
        special = draw.get("special_numbers", [])
        assert len(special) <= 1 and all(1 <= n <= 49 and n not in draw["numbers"] for n in special)
    assert history[-1]["draw_no"] == payload["latest_draw_no"], "近期快照落後歷史資料"
    write_json(snapshot_path, history)
    return history


def replay(history, ranker, method):
    trials = []
    position_hits, ball_hits, ball_frequency = Counter(), Counter(), Counter()
    selections, group_hits = Counter(), Counter()
    years = defaultdict(list)
    for index in range(200, len(history)):
        previous = history[index - 200 : index]
        actual = history[index]
        ranking = ranker(previous, 49)
        numbers = [entry["number"] for entry in ranking]
        assert sorted(numbers) == list(range(1, 50))
        assert previous[-1]["draw_date"] < actual["draw_date"]
        wins = set(actual["numbers"])
        positions = [numbers.index(n) + 1 for n in actual["numbers"]]
        position_hits.update(positions)
        ball_hits.update(set(numbers[:5]) & wins)
        ball_frequency.update(wins)
        if method == "counts":
            assert all(0 <= r["count"] <= 4 for r in ranking)
            selections.update(r["count"] for r in ranking)
            group_hits.update(r["count"] for r in ranking if r["number"] in wins)
        trial = dict(
            anchor_draw_no=previous[-1]["draw_no"],
            anchor_date=previous[-1]["draw_date"],
            target_draw_no=actual["draw_no"],
            target_date=actual["draw_date"],
            actual=actual["numbers"],
            special_numbers=actual.get("special_numbers", []),
            winning_ranks=positions,
            ranking=ranking,
            hits={str(k): len(set(numbers[:k]) & wins) for k in TOPS},
        )
        trials.append(trial)
        years[actual["draw_date"][:4]].append(trial)
    summary = []
    for top in TOPS:
        counts = Counter(t["hits"][str(top)] for t in trials)
        summary.append(
            dict(
                top=top,
                average_hits=sum(n * c for n, c in counts.items()) / len(trials),
                random_average=6 * top / 49,
                at_least_one=1 - counts[0] / len(trials),
                distribution={str(n): counts[n] for n in range(7)},
            )
        )
    assert sum(position_hits.values()) == len(trials) * 6 == sum(ball_frequency.values())
    assert sum(ball_hits.values()) == sum(t["hits"]["5"] for t in trials)
    return dict(
        method=method,
        source_start=history[0]["draw_date"],
        source_end=history[-1]["draw_date"],
        source_draws=len(history),
        warmup=200,
        trial_start=trials[0]["target_date"],
        trial_end=trials[-1]["target_date"],
        trials=len(trials),
        latest_draw_no=history[-1]["draw_no"],
        latest_ranking=ranker(history[-200:], 49),
        summary=summary,
        position_hits=[dict(rank=n, hits=position_hits[n]) for n in range(1, 50)],
        ball_hits=[dict(number=n, hits=ball_hits[n]) for n in range(1, 50)],
        ball_frequency=[dict(number=n, hits=ball_frequency[n]) for n in range(1, 50)],
        count_groups=[
            dict(
                count=n,
                selections=selections[n],
                hits=group_hits[n],
                hit_rate=group_hits[n] / selections[n] if selections[n] else None,
            )
            for n in range(4, -1, -1)
        ],
        yearly=[
            dict(
                year=y,
                trials=len(ts),
                **{f"top{k}": sum(t["hits"][str(k)] for t in ts) / len(ts) for k in TOPS},
            )
            for y, ts in sorted(years.items())
        ],
        details=trials,
    )


def ball_strip(items):
    ordered = sorted(items, key=lambda x: (-x["hits"], x["number"]))
    cells = "".join(
        f'<td class="hit-group-{i // 5} {"group-end" if i % 5 == 4 else ""}"><span class="ball">{x["number"]:02}</span><span class="hits">{x["hits"]}</span></td>'
        for i, x in enumerate(ordered)
    )
    return f'<div class="scroll compact-hit-ranking"><table aria-label="49個球號，每5格分色"><tbody><tr>{cells}</tr></tbody></table></div>'


def render_report(p):
    method = p["method"]
    title = "相鄰次數歷史試算" if method == "counts" else "相鄰分數歷史試算"
    name = "649-adjacent-counts-backtest" if method == "counts" else "649-adjacent-backtest"
    write_json(TARGET / f"{name}.json", p)
    rule = (
        "每範圍同號最多計1次，跨範圍累計0～4次。"
        if method == "counts"
        else "每範圍首次出現1分，同範圍每多出現一次加0.1分，跨範圍累加。"
    )
    body = f'<p>資料：{p["source_start"]}～{p["source_end"]}，共{p["source_draws"]:,}期。前200期建立統計，回測{p["trial_start"]}～{p["trial_end"]}，共{p["trials"]:,}期。</p><p>依當時近20／50／100／200期次數分組，取當期6個主號的上下左右相鄰球。{rule}同分球號升序，固定取前N名對照下一期6個主號，特別號不計。未使用未來資料。隨機基準為6×N／49。</p><p>使用本機官方來源紀錄與近期官方快照；資料覆蓋與缺號請見<a href="649-source-gaps.html">來源查核</a>。本次未重新連線核對完整官方歷史。</p>'
    key = "count" if method == "counts" else "score"
    latest = "".join(
        f"<td><small>{x[key]:g}{'次' if method == 'counts' else '分'}</small><b>{x['number']:02}</b></td>"
        for x in p["latest_ranking"]
    )
    body += f'<h2>最新49號排名 · 截至{p["latest_draw_no"]}期</h2><div id="latest-ranking" class="scroll ranking-strip"><table><tbody><tr>{latest}</tr></tbody></table></div>'
    header = (
        "<tr><th>範圍</th><th>平均命中</th><th>隨機基準</th><th>至少中1顆</th>"
        + "".join(f"<th>中{n}顆期數</th>" for n in range(7))
        + "</tr>"
    )
    rows = "".join(
        f"<tr><th>前{x['top']}名</th><td>{x['average_hits']:.4f}</td><td>{x['random_average']:.4f}</td><td>{x['at_least_one']:.2%}</td>"
        + "".join(f"<td>{x['distribution'][str(n)]}</td>" for n in range(7))
        + "</tr>"
        for x in p["summary"]
    )
    body += f'<h2>命中統計</h2><div class="scroll"><table>{header}{rows}</table></div>'
    positions = "".join(
        f"<td data-rank=\"{x['rank']}\" data-hits=\"{x['hits']}\"><small>第{index + 1}名</small>"
        f"<small>本期球號 {p['latest_ranking'][x['rank'] - 1]['number']:02}</small>"
        f"<b>{x['hits']}</b><small>原第{x['rank']}名</small></td>"
        for index, x in enumerate(sorted(p["position_hits"], key=lambda x: (-x["hits"], x["rank"])))
    )
    body += f'<h2>累計命中次數排名 · 由高到低</h2><p>依累計命中次數由高到低編為第1～49名，同次數依原排名位置排序。每格顯示截至第{p["latest_draw_no"]}期對應的球號，底下註明原排名位置。累計次數統計的是歷期排名位置，並非本期球號的歷史命中次數。</p><div id="position-hits" class="scroll ranking-strip"><table><tr>{positions}</tr></table></div>'
    body += (
        '<section id="ball-frequency-ranking"><h2>49球號開出次數</h2>'
        + ball_strip(p["ball_frequency"])
        + '</section><section id="colored-hit-ranking"><h2>相鄰排名前5名 · 各球號命中次數</h2><p>此處為命中次數，入選次數可能不同，並非命中率。</p>'
        + ball_strip(p["ball_hits"])
        + "</section>"
    )
    if method == "counts":
        rows = "".join(
            f"<tr><th>{g['count']}次</th><td>{g['selections']}</td><td>{g['hits']}</td><td>{g['hit_rate']:.2%}</td></tr>"
            if g["hit_rate"] is not None
            else f"<tr><th>{g['count']}次</th><td>0</td><td>0</td><td>—</td></tr>"
            for g in p["count_groups"]
        )
        body += (
            '<h2>各相鄰次數組別</h2><p>每球隨機基準6／49＝12.24%。</p><div class="scroll"><table><tr><th>相鄰次數</th><th>入組球次</th><th>命中球次</th><th>每球命中率</th></tr>'
            + rows
            + "</table></div>"
        )
    rows = "".join(
        f"<tr><th>{y['year']}</th><td>{y['trials']}</td>"
        + "".join(f"<td>{y[f'top{k}']:.4f}</td>" for k in TOPS)
        + "</tr>"
        for y in p["yearly"]
    )
    body += (
        '<h2>逐年結果</h2><div class="scroll"><table><tr><th>年</th><th>回測期數</th>'
        + "".join(f"<th>前{k}名平均命中</th>" for k in TOPS)
        + "</tr>"
        + rows
        + "</table></div>"
    )
    rows = "".join(
        f"<tr><td>{t['target_date']}</td><td>{t['target_draw_no']}</td><td>{', '.join(f'{n:02}' for n in t['actual'])}</td><td>{', '.join(f'{n:02}' for n in t['special_numbers']) or '—'}</td>"
        + "".join(f"<td>{t['hits'][str(k)]}</td>" for k in TOPS)
        + "<td>"
        + " → ".join(f"{r['number']:02}" for r in t["ranking"])
        + "</td></tr>"
        for t in reversed(p["details"])
    )
    body += (
        f'<p>歷史統計不代表未來結果。<a href="{name}.json">完整逐期排名JSON</a></p><details><summary>全部{p["trials"]:,}期明細</summary><div class="scroll"><table><tr><th>日期</th><th>期號</th><th>主號</th><th>特別號（不計分）</th>'
        + "".join(f"<th>前{k}名命中</th>" for k in TOPS)
        + "<th>49球排名順序</th></tr>"
        + rows
        + "</table></div></details>"
    )
    page(f"{name}.html", title, body)


def build_combined(history):
    reference_path = ROOT / "docs/data/649-pilio-reference.json"
    reference = (
        json.loads(reference_path.read_text(encoding="utf-8")) if reference_path.exists() else None
    )
    cutoff = history[-1]["draw_date"]
    matched = reference is not None and reference["source_date"] == cutoff
    brief_path = ROOT / "docs/data/649-aibrief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else None
    matched = (
        matched
        and brief is not None
        and reference.get("article_sha256") == brief.get("article_sha256")
    )
    ranking = score_rank(history[-200:], 49)
    for entry in ranking:
        tags = (
            [name for name, ns in reference["categories"].items() if entry["number"] in ns]
            if matched
            else []
        )
        entry.update(
            tags=tags, bonus=len(tags) / 10, combined=(round(entry["score"] * 10) + len(tags)) / 10
        )
    ranking.sort(key=lambda x: (-x["combined"], x["number"]))
    result = dict(
        date=cutoff,
        latest_draw_no=history[-1]["draw_no"],
        reference=reference,
        brief_applied=matched,
        ranking=ranking,
        historical_backtest=False,
    )
    write_json(ROOT / "docs/data/649-combined.json", result)
    notice = (
        "同截止日快報的四類提及各加0.1分；冷門、久未開及條件拖牌不加減分。"
        if matched
        else "AI快報尚無相同截止日的已核對分類資料，本頁先顯示相鄰分數，快報加分為0。"
    )
    body = f'<p id="status">資料截至{cutoff} · 第{history[-1]["draw_no"]}期 · 下一期參考排名</p><p>{notice}此為目前資料合併參考，尚無逐日快報快照作全歷史回測。</p>'
    cells = "".join(
        f"<td><small>{x['combined']:.1f}分</small><b>{x['number']:02}</b></td>" for x in ranking
    )
    body += f'<div id="numbers" class="scroll ranking-strip"><table><tbody><tr>{cells}</tr></tbody></table></div><details><summary>展開逐號計分</summary><div class="scroll"><table><tr><th>球號</th><th>相鄰分數</th><th>快報加分</th><th>合計</th><th>類別</th></tr>'
    body += "".join(
        f"<tr><td>{x['number']:02}</td><td>{x['score']:.1f}</td><td>{x['bonus']:.1f}</td><td>{x['combined']:.1f}</td><td>{html.escape('、'.join(x['tags'])) or '—'}</td></tr>"
        for x in ranking
    )
    body += '</table></div></details><p><a href="../data/649-combined.json">逐號計分JSON</a></p><section data-aibrief aria-live="polite"></section>'
    page(
        "649-combined-reference.html",
        "相鄰分數＋AI快報",
        body,
        '<script src="649-aibrief.js"></script>',
    )


def build_audit(history):
    records = [
        dict(**d, ball_set=None, direction=None, loading_start_number=None, video_status="待核對")
        for d in history
    ]
    write_json(TARGET / "649-full-audit.json", records)
    by_year = defaultdict(list)
    for d in history:
        by_year[d["draw_date"][:4]].append(int(d["draw_no"][-6:]))
    rows = []
    gaps = []
    for year, numbers in sorted(by_year.items()):
        missing = sorted(set(range(min(numbers), max(numbers) + 1)) - set(numbers))
        gaps.extend(dict(year=year, period=n) for n in missing)
        rows.append(
            f"<tr><th>{year}</th><td>{len(numbers)}</td><td>{min(numbers)}</td><td>{max(numbers)}</td><td>{'、'.join(map(str, missing)) or '範圍內無缺號'}</td></tr>"
        )
    write_json(
        TARGET / "649-source-gaps.json",
        dict(
            source_start=history[0]["draw_date"],
            source_end=history[-1]["draw_date"],
            gaps=gaps,
            scope="僅檢查已有資料每年首末期之間的期號連續性；不推定範圍外資料完整",
        ),
    )
    page(
        "649-source-gaps.html",
        "來源與缺號查核",
        f'<p>現有資料{history[0]["draw_date"]}～{history[-1]["draw_date"]}，共{len(history):,}期。僅檢查各年已有首末期之間的期號連續性，未推定範圍外資料完整；未重新核對官方全歷史或影片。</p><div class="scroll"><table><tr><th>年</th><th>期數</th><th>起始期次</th><th>末期次</th><th>範圍內缺號</th></tr>{"".join(rows)}</table></div><p><a href="649-source-gaps.json">下載查核JSON</a></p>',
    )
    body = f'<p id="coverage">官方來源資料{history[0]["draw_date"]}～{history[-1]["draw_date"]}，共{len(history):,}期。主號與特別號分列；影片球組、方向、裝球起始號碼尚未核對。</p><nav><a href="#audit">完整核對資料</a><a href="#statistics">分類統計</a><a href="#recent">近6～48期統計</a><a href="#overlay">位置疊加</a><a href="649-source-gaps.html">來源缺號查核</a><a href="649-full-audit.json" download>下載完整JSON</a></nav>'
    body += """<section id="audit"><h2>完整核對資料</h2><div class="filters"><label>起始日期<input type="date" id="from"></label><label>截止日期<input type="date" id="to"></label><label>主號包含<input type="number" min="1" max="49" id="number"></label><label>影片狀態<select id="state"><option value="">全部</option><option>待核對</option><option>已核對</option></select></label><button id="reset">清除篩選</button><button id="export">匯出篩選CSV</button></div><p id="result" aria-live="polite"></p><div class="scroll"><table><thead><tr><th>日期</th><th>期號</th><th>主號</th><th>特別號</th><th>球組</th><th>方向</th><th>裝球起始</th><th>影片狀態</th></tr></thead><tbody id="rows"></tbody></table></div><p><button id="previous">上一頁</button> <span id="page"></span> <button id="next">下一頁</button></p></section><section id="statistics"><h2>球組與方向統計</h2><p>目前沒有大樂透影片核對紀錄，球組、方向及裝球起始統計待核對後建立。</p></section><section id="recent"><h2>近6／12／18／24／30／36／42／48期主號統計</h2><label>統計截止期<select id="cutoff"></select></label><p>八組使用相同截止期，依實際開獎期累計，特別號不計。</p><div id="recent-panels"></div></section><section id="overlay"><h2>位置疊加與空白格比較</h2><p><a href="handwritten-649-overlay.html">開啟完整疊加頁</a></p><iframe src="handwritten-649-overlay.html" title="大樂透近6～48期疊加" loading="lazy"></iframe></section>"""
    page("649-dashboard.html", "完整總覽", body, '<script src="649-dashboard.js"></script>')
    page("649-full-audit.html", "完整核對表", body, '<script src="649-dashboard.js"></script>')


def build():
    history = load_history()
    for ranker, method in ((score_rank, "scores"), (count_rank, "counts")):
        report = replay(history, ranker, method)
        render_report(report)
        if method == "scores":
            body = (
                f'<p>每期取相鄰分數前5名，對照下一期6個主號；特別號不計。回測{report["trial_start"]}～{report["trial_end"]}，共{report["trials"]:,}期。命中次數並非命中率，同分球號升序。</p><section id="colored-hit-ranking"><h2>相鄰分數前5名 · 各球號命中次數</h2>'
                + ball_strip(report["ball_hits"])
                + '</section><section data-aibrief aria-live="polite"></section>'
            )
            page(
                "649-top5-hit-ranking.html",
                "49球號命中統計",
                body,
                '<script src="649-aibrief.js"></script>',
            )
    build_combined(history)
    build_audit(history)
    reference = (TARGET / "649-adjacent-reference.html").read_text(encoding="utf-8")
    for alias in ("649-adjacent-count-grid.html", "649-adjacent-count-row.html"):
        (TARGET / alias).write_text(reference, encoding="utf-8")
    print(
        f"Lotto modes: {len(history)} official draws, {len(history) - 200} replay trials per method"
    )


if __name__ == "__main__":
    build()
