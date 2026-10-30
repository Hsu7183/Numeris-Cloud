"""Replay the four-scope adjacency count method from the reference page."""

# ruff: noqa: E501 -- embedded report markup.
from __future__ import annotations

import json
from collections import Counter

from scripts.backtest_539_adjacent import ROOT, TOPS, load


def rank(history: list[dict], ball_count: int = 39) -> list[dict]:
    totals = Counter()
    for limit in (20, 50, 100, 200):
        frequency = Counter(n for d in history[-limit:] for n in d["numbers"])
        rows = [
            [n for n in range(1, ball_count + 1) if frequency[n] == count]
            for count in sorted(set(frequency.values()), reverse=True)
            if count
        ]
        adjacent = set()
        for target in history[-1]["numbers"]:
            ri = next(i for i, row in enumerate(rows) if target in row)
            ci = rows[ri].index(target)
            for r, c in ((ri, ci - 1), (ri, ci + 1), (ri - 1, ci), (ri + 1, ci)):
                if 0 <= r < len(rows) and 0 <= c < len(rows[r]):
                    adjacent.add(rows[r][c])
        totals.update(adjacent)
    return [
        dict(number=n, count=totals[n])
        for n in sorted(range(1, ball_count + 1), key=lambda n: (-totals[n], n))
    ]


def main() -> None:
    draws, audit = load()
    trials = []
    position_hits = Counter()
    count_trials = Counter()
    count_hits = Counter()
    for i in range(200, len(draws)):
        history = draws[i - 200 : i]
        ranking = rank(history)
        actual = draws[i]
        numbers = [r["number"] for r in ranking]
        assert len(set(numbers)) == 39
        assert history[-1]["draw_date"] < actual["draw_date"]
        assert all(0 <= r["count"] <= 4 for r in ranking)
        wins = set(actual["numbers"])
        position_hits.update(numbers.index(n) + 1 for n in wins)
        count_trials.update(r["count"] for r in ranking)
        count_hits.update(r["count"] for r in ranking if r["number"] in wins)
        trials.append(
            dict(
                target_draw_no=actual["draw_no"],
                target_date=actual["draw_date"],
                anchor_draw_no=history[-1]["draw_no"],
                actual=actual["numbers"],
                ranking=ranking,
                hits={str(k): len(set(numbers[:k]) & wins) for k in TOPS},
            )
        )
    summary = []
    for k in TOPS:
        distribution = Counter(t["hits"][str(k)] for t in trials)
        summary.append(
            dict(
                top=k,
                average_hits=sum(h * n for h, n in distribution.items()) / len(trials),
                random_average=5 * k / 39,
                at_least_one=1 - distribution[0] / len(trials),
                distribution={str(h): distribution[h] for h in range(6)},
            )
        )
    assert sum(position_hits.values()) == len(trials) * 5
    assert sum(count_hits.values()) == len(trials) * 5
    result = dict(
        method="four_scope_presence_count_0_to_4",
        source_start=draws[0]["draw_date"],
        source_end=draws[-1]["draw_date"],
        source_draws=len(draws),
        warmup=200,
        trial_start=trials[0]["target_date"],
        trials=len(trials),
        audit=audit,
        summary=summary,
        latest_draw_no=draws[-1]["draw_no"],
        latest_ranking=rank(draws[-200:]),
        position_hits=[dict(rank=r, hits=position_hits[r]) for r in range(1, 40)],
        count_groups=[
            dict(
                count=c,
                selections=count_trials[c],
                hits=count_hits[c],
                hit_rate=count_hits[c] / count_trials[c] if count_trials[c] else None,
            )
            for c in range(4, -1, -1)
        ],
        details=trials,
    )
    target = ROOT / "docs/539-adjacent-counts-backtest.json"
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(target)
    render(result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("source_draws", "source_end", "trials", "summary", "count_groups")
            },
            indent=2,
        )
    )


def render(p: dict) -> None:
    summary = "".join(
        "<tr>"
        + f"<th>前{s['top']}名</th><td>{s['average_hits']:.4f}</td><td>{s['random_average']:.4f}</td><td>{s['at_least_one']:.2%}</td>"
        + "".join(f"<td>{s['distribution'][str(h)]}</td>" for h in range(6))
        + "</tr>"
        for s in p["summary"]
    )
    positions = "".join(
        f"<td data-rank=\"{x['rank']}\" data-hits=\"{x['hits']}\"><small>第{x['rank']}名</small>"
        f"<b class=\"position-ball\">{p['latest_ranking'][x['rank'] - 1]['number']:02}</b>"
        f"<span class=\"position-hit-count\">{x['hits']}次</span></td>"
        for x in sorted(p["position_hits"], key=lambda item: (-item["hits"], item["rank"]))
    )
    latest = "".join(
        f"<td><small>{x['count']}次</small><b>{x['number']:02}</b></td>"
        for x in p["latest_ranking"]
    )
    groups = "".join(
        f"<tr><th>{g['count']}次</th><td>{g['selections']}</td><td>{g['hits']}</td><td>{g['hit_rate']:.2%}</td></tr>"
        for g in p["count_groups"]
    )
    details = "".join(
        f"<tr><td>{t['target_date']}</td><td>{t['target_draw_no']}</td><td>"
        + ",".join(f"{n:02}" for n in t["actual"])
        + "</td>"
        + "".join(f"<td>{t['hits'][str(k)]}</td>" for k in TOPS)
        + "<td>"
        + " → ".join(f"{r['number']:02}" for r in t["ranking"])
        + "</td>"
        + "</tr>"
        for t in reversed(p["details"])
    )
    page = f"""<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>539 相鄰次數歷史排名試算</title>
<style>body{{margin:24px;background:#eef2ea;color:#193e30;font-family:"Microsoft JhengHei",sans-serif}}table{{border-collapse:collapse;width:100%;background:#fffefa;font-variant-numeric:tabular-nums}}td,th{{border:1px solid #c7d4c7;padding:10px;text-align:center;white-space:nowrap}}th{{background:#e3eddd}}.scroll{{overflow:auto;margin:20px 0}}b,small{{display:block}}small{{color:#798a7e;margin-bottom:8px}}b{{font-size:22px}}p{{line-height:1.8}}a{{color:#076b50}}</style>
<style>.ranking-strip{{min-width:0;container-type:inline-size;overflow:visible}}.ranking-strip table{{width:100%;table-layout:fixed}}.ranking-strip td{{width:calc(100% / 39);padding:8px 0}}.ranking-strip small{{font-size:clamp(1px,.65cqw,10px)}}.ranking-strip b{{font-size:clamp(1px,1.15cqw,16px)}}#latest-ranking b{{font-size:clamp(1px,1.45cqw,20px)}}</style>
<a href="539-adjacent-reference.html">← 今彩539 · 相鄰次數</a><h1>相鄰次數 · 全歷史排名試算</h1>
<p>資料{p["source_start"]}～{p["source_end"]}共{p["source_draws"]:,}期；前200期建立統計，回測{p["trial_start"]}起共{p["trials"]:,}期。</p>
<p>完全依相鄰次數頁：近20／50／100／200期各範圍內取當期5顆球的上下左右相鄰球，同一範圍同號最多計1次，跨範圍累計0～4次；次數高者在前，同次數依球號升序。固定取前N名對照下一期5顆獎號，未使用未來資料。</p>
<p>使用本機官方來源紀錄合併近期快照，排除測試資料，衝突由快照核對覆蓋；各年期號連續。本次未重新連線核對官方。</p>
<h2>最新39號排名 · 截至{p["latest_draw_no"]}期</h2><div id="latest-ranking" class="scroll ranking-strip"><table aria-label="最新39個球號排名，同一行完整顯示"><tr>{latest}</tr></table></div>
<h2>命中統計</h2><div class="scroll"><table><tr><th>範圍</th><th>每期平均命中</th><th>隨機基準</th><th>至少中1顆</th>{"".join(f"<th>中{n}顆期數</th>" for n in range(6))}</tr>{summary}</table></div>
<h2>第1～39名對應球號 · 累計命中次數由多到少</h2><p>上排為原排名，中排為截至{p["latest_draw_no"]}期該排名對應的球號，下排為該排名的歷史累計命中次數；同次數依原排名排序。每期排名對應球號會變動，歷史命中次數統計的是排名位置。</p><style>#position-hits .position-ball{{font-size:clamp(1px,1.45cqw,20px);margin:6px 0}}#position-hits .position-hit-count{{display:block;font-size:clamp(1px,.85cqw,12px);color:#526b5c}}</style><div id="position-hits" class="scroll ranking-strip"><table aria-label="第1至39名對應球號，按排名歷史命中次數由多到少排列"><tr>{positions}</tr></table></div>
<h2>各相鄰次數組別</h2><p>入組球次為每期組內球號數的加總；命中率為該組入選球號下一期開出的比例。隨機基準5／39＝12.82%。</p><table><tr><th>相鄰次數</th><th>入組球次</th><th>命中球次</th><th>每球命中率</th></tr>{groups}</table>
<p>歷史結果供參考。<a href="539-adjacent-counts-backtest.json">完整逐期排名JSON</a> · <a href="539-adjacent-backtest.html">原相鄰分數試算</a></p>
<details><summary>全部{p["trials"]:,}期明細與39號排名順序</summary><p>每列排名依前一期已知資料計算，由第1名至第39名，對照該列日期的開獎結果。</p><div class="scroll"><table><tr><th>日期</th><th>期號</th><th>獎號</th>{"".join(f"<th>前{k}名命中</th>" for k in TOPS)}<th>依前一期資料計算的39號排名（第1→39名）</th></tr>{details}</table></div></details></html>"""
    (ROOT / "docs/539-adjacent-counts-backtest.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
