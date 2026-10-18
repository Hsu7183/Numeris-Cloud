"""Replay the output.html adjacency ranking without future draw leakage."""

# ruff: noqa: E501 -- standalone report HTML contains long literal lines.

from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANGES = (20, 50, 100, 200)
TOPS = (5, 10, 15, 20)


def rank(history: list[dict]) -> list[dict]:
    """history is oldest first, including the most recently known draw."""
    scores = Counter()
    for limit in RANGES:
        counts = Counter(n for draw in history[-limit:] for n in draw["numbers"])
        groups = [
            [n for n in range(1, 40) if counts[n] == count]
            for count in sorted(set(counts.values()), reverse=True)
            if count
        ]
        appearances = Counter()
        for target in history[-1]["numbers"]:
            ri = next(i for i, row in enumerate(groups) if target in row)
            ci = groups[ri].index(target)
            neighbors = set()
            for r, c in ((ri, ci - 1), (ri, ci + 1), (ri - 1, ci), (ri + 1, ci)):
                if 0 <= r < len(groups) and 0 <= c < len(groups[r]):
                    neighbors.add(groups[r][c])
            neighbors.discard(target)
            appearances.update(neighbors)
        for number, count in appearances.items():
            scores[number] += 10 + count - 1
    # Integer tenths avoid floating point tie-breaking differences.
    return [
        dict(number=n, score=scores[n] / 10)
        for n in sorted(range(1, 40), key=lambda n: (-scores[n], n))
    ]


def load() -> tuple[list[dict], dict]:
    db = ROOT / "data/database/numeris.sqlite3"
    if db.exists():
        with sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True) as connection:
            rows = connection.execute("""
            SELECT d.id,d.draw_no,d.draw_date,d.verification_status,n.number_value
            FROM draws d JOIN games g ON g.id=d.game_id
            JOIN draw_numbers n ON n.draw_id=d.id
            WHERE g.game_code='TW_DAILY539' AND d.source_status='official'
              AND n.pool_code='main' AND n.is_special=0
            ORDER BY d.draw_date,d.draw_no,n.number_value
            """).fetchall()
    else:
        # GitHub Pages runners use the audited official history, never a fixture DB.
        snapshot = json.loads((ROOT / "reports/539-adjacent-source.json").read_text(encoding="utf-8"))
        rows = [
            (i, draw["draw_no"], draw["draw_date"], "verified", number)
            for i, draw in enumerate(snapshot)
            for number in draw["numbers"]
        ]
    merged = {}
    conflicts = set()
    for _, number, date, status, ball in rows:
        merged.setdefault(number, dict(draw_no=number, draw_date=date, numbers=[]))[
            "numbers"
        ].append(ball)
        if status == "conflict":
            conflicts.add(number)
    recent = json.loads((ROOT / "docs/data/daily539.json").read_text(encoding="utf-8"))
    conflict_count = len(conflicts)
    replacements = []
    for draw in recent["draws"]:
        assert draw["source_status"] == "official", draw
        key = draw["draw_no"]
        if key in merged and merged[key]["numbers"] != sorted(draw["numbers"]):
            replacements.append(
                dict(draw_no=key, old=merged[key]["numbers"], new=sorted(draw["numbers"]))
            )
        merged[key] = dict(
            draw_no=key, draw_date=draw["draw_date"], numbers=sorted(draw["numbers"])
        )
        conflicts.discard(key)
    assert not conflicts, f"Unresolved conflicts: {conflicts}"
    draws = sorted(merged.values(), key=lambda d: (d["draw_date"], d["draw_no"]))
    assert len({d["draw_date"] for d in draws}) == len(draws)
    by_year = defaultdict(list)
    for draw in draws:
        assert len(set(draw["numbers"])) == len(draw["numbers"]) == 5
        assert all(1 <= n <= 39 for n in draw["numbers"])
        by_year[draw["draw_date"][:4]].append(int(draw["draw_no"][-6:]))
    for year, numbers in by_year.items():
        assert min(numbers) == 1 and len(numbers) == max(numbers), (year, "missing periods")
    return draws, dict(
        database_official_draws=len({r[1] for r in rows}),
        recent_snapshot_draws=len(recent["draws"]),
        resolved_conflict_records=conflict_count,
        changed_numbers=replacements,
        yearly_counts={year: len(ns) for year, ns in by_year.items()},
    )


def main() -> None:
    draws, audit = load()
    source_export = ROOT / "reports/539-adjacent-source.json"
    source_export.parent.mkdir(parents=True, exist_ok=True)
    source_export.write_text(json.dumps(draws, ensure_ascii=False), encoding="utf-8")
    trials = []
    rank_hits = Counter()
    yearly = defaultdict(list)
    for target_index in range(200, len(draws)):
        history = draws[target_index - 200 : target_index]
        ordered = rank(history)
        actual = draws[target_index]
        numbers = [x["number"] for x in ordered]
        positions = [numbers.index(n) + 1 for n in actual["numbers"]]
        rank_hits.update(positions)
        hits = {str(k): len(set(numbers[:k]) & set(actual["numbers"])) for k in TOPS}
        trial = dict(
            anchor_draw_no=history[-1]["draw_no"],
            anchor_date=history[-1]["draw_date"],
            target_draw_no=actual["draw_no"],
            target_date=actual["draw_date"],
            actual=actual["numbers"],
            winning_ranks=positions,
            hits=hits,
            ranking=ordered,
        )
        assert history[-1]["draw_date"] < actual["draw_date"]
        assert len(ordered) == len(set(numbers)) == 39
        assert sum(1 for p in positions if p <= 5) == hits["5"]
        trials.append(trial)
        yearly[actual["draw_date"][:4]].append(trial)
    assert sum(rank_hits.values()) == len(trials) * 5
    summaries = []
    for k in TOPS:
        values = [t["hits"][str(k)] for t in trials]
        summaries.append(
            dict(
                top=k,
                average_hits=sum(values) / len(values),
                random_average=5 * k / 39,
                hit_distribution={str(h): values.count(h) for h in range(6)},
                at_least_one=sum(v > 0 for v in values) / len(values),
            )
        )
    # Current known fixture independently calculated from the existing browser algorithm.
    latest = rank(draws[-200:])
    if draws[-1]["draw_no"] == "115000251":
        assert [(x["number"], x["score"]) for x in latest[:5]] == [
            (13, 4.0),
            (20, 3.1),
            (26, 3.1),
            (15, 3.0),
            (16, 3.0),
        ]
    report = dict(
        method="20/50/100/200; first appearance 1, additional 0.1; ties by ball ascending",
        source_start=draws[0]["draw_date"],
        source_end=draws[-1]["draw_date"],
        source_draws=len(draws),
        warmup_draws=200,
        trials=len(trials),
        trial_start=trials[0]["target_date"],
        trial_end=trials[-1]["target_date"],
        audit=audit,
        summary=summaries,
        rank_hits=[dict(rank=r, hits=rank_hits[r]) for r in range(1, 40)],
        yearly=[
            dict(
                year=y,
                trials=len(ts),
                **{f"top{k}": sum(t["hits"][str(k)] for t in ts) / len(ts) for k in TOPS},
            )
            for y, ts in yearly.items()
        ],
        latest_ranking=latest,
        details=trials,
    )
    destination = ROOT / "docs/539-adjacent-backtest.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    render(report)
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("details", "audit", "latest_ranking", "yearly", "rank_hits")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("Changed overlapping draws:", len(audit["changed_numbers"]))


def render(report: dict) -> None:
    ball_hits = Counter()
    for trial in report["details"]:
        picks = {item["number"] for item in trial["ranking"][:5]}
        ball_hits.update(picks & set(trial["actual"]))
    ordered_balls = sorted(range(1, 40), key=lambda n: (-ball_hits[n], n))
    ball_cells = "".join(
        f'<td class="hit-group-{i // 5} {"group-end" if (i + 1) % 5 == 0 else ""}" '
        f'aria-label="第{i + 1}位，{n:02}號，命中{ball_hits[n]}次">'
        f'<span class="ball">{n:02}</span><span class="hits">{ball_hits[n]}</span></td>'
        for i, n in enumerate(ordered_balls)
    )
    summary_rows = "".join(
        f"<tr><th>前{s['top']}名</th><td>{s['average_hits']:.4f}</td><td>{s['random_average']:.4f}</td><td>{s['at_least_one']:.2%}</td>"
        + "".join(f"<td>{s['hit_distribution'][str(n)]}</td>" for n in range(6))
        + "</tr>"
        for s in report["summary"]
    )
    years = "".join(
        f"<tr><th>{y['year']}</th><td>{y['trials']}</td>"
        + "".join(f"<td>{y[f'top{k}']:.4f}</td>" for k in TOPS)
        + "</tr>"
        for y in report["yearly"]
    )
    ranks = "".join(
        f"<td><small>{r['rank']}名</small><br>{r['hits']}次</td>" for r in report["rank_hits"]
    )
    details = "".join(
        "<tr><td>"
        + html.escape(t["target_date"])
        + "</td><td>"
        + t["target_draw_no"]
        + "</td><td>"
        + ",".join(f"{n:02}" for n in t["actual"])
        + "</td><td>"
        + ",".join(map(str, t["winning_ranks"]))
        + "</td>"
        + "".join(f"<td>{t['hits'][str(k)]}</td>" for k in TOPS)
        + "</tr>"
        for t in reversed(report["details"])
    )
    page = f"""<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>539 相鄰分數歷史試算</title>
<style>body{{font-family:"Microsoft JhengHei",sans-serif;background:#f5f7f2;color:#193e30;margin:24px}}main{{max-width:1400px;margin:auto}}table{{border-collapse:collapse;width:100%;background:white;font-variant-numeric:tabular-nums}}th,td{{border:1px solid #ccd8ce;padding:8px;text-align:center;white-space:nowrap}}th{{background:#e4eddf}}.scroll{{overflow:auto;margin:18px 0}}p{{line-height:1.8}}a{{color:#076b50}}small{{color:#66796d}}h1{{font-size:1.6rem}}</style><main>
<link rel="stylesheet" href="539-hit-ranking.css?v=1">
<a href="output.html">← 相鄰分數排名</a><h1>今彩539 · 相鄰分數歷史試算</h1>
<p>資料：{report["source_start"]}～{report["source_end"]}，共 {report["source_draws"]:,} 期。前200期建立統計，實際回測 {report["trials"]:,} 期（{report["trial_start"]}～{report["trial_end"]}）。</p>
<p>每期以當時最近20／50／100／200期的次數分組，從當期5顆球取左右上下相鄰球。同範圍首次1分，重複每次加0.1分，跨範圍加總；同分依球號小到大。用所得排名對照<strong>下一期</strong>獎號，未使用未來資料。</p>
<p>僅使用官方來源紀錄或已核對的官方歷史快照，排除測試資料；{report['audit']['resolved_conflict_records']}期資料庫衝突標記由近期官方來源快照覆蓋。各年期號自第1期至最後一期連續無缺號；本次未重新連線核對完整歷史官方資料。前N名遇同分仍固定取N顆。以下隨機基準為39顆中固定選N顆的理論平均命中數。</p>
<h2>命中統計</h2><div class="scroll"><table><thead><tr><th>排名範圍</th><th>平均命中</th><th>隨機基準</th><th>至少中1顆</th>{"".join(f"<th>中{n}顆期數</th>" for n in range(6))}</tr></thead><tbody>{summary_rows}</tbody></table></div>
<h2>39個排名各自命中次數</h2><div class="scroll"><table><tr>{ranks}</tr></table></div>
<section id="colored-hit-ranking"><h2>相鄰分數前5名 · 各球號命中次數</h2>
<p>每期取相鄰分數前5名，對照下一期獎號。由命中次數高到低排列，每5格分色；上排球號，下排命中次數。同分優先取較小球號，入選次數可能不同，此處為命中次數而非命中率。</p>
<div class="scroll"><table aria-label="39個球號命中次數，每5格分色"><tbody><tr>{ball_cells}</tr></tbody></table></div></section>
<h2>逐年結果</h2><div class="scroll"><table><tr><th>年</th><th>回測期數</th>{"".join(f"<th>前{k}名平均命中</th>" for k in TOPS)}</tr>{years}</table></div>
<p>歷史試算不代表未來結果。<a href="539-adjacent-backtest.json">完整逐期排名資料</a></p>
<details><summary>展開全部 {report["trials"]:,} 期明細（由新到舊）</summary><div class="scroll"><table><tr><th>開獎日</th><th>期號</th><th>開獎球號</th><th>各獎號所在排名</th>{"".join(f"<th>前{k}名命中</th>" for k in TOPS)}</tr>{details}</table></div></details></main></html>"""
    (ROOT / "docs/539-adjacent-backtest.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
