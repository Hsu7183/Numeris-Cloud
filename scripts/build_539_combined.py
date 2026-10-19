"""Build a reviewable current snapshot combining adjacency scores and brief mentions."""

# ruff: noqa: E501 -- literal standalone page markup and JavaScript.

from __future__ import annotations

import json
from datetime import date, timedelta

from scripts.backtest_539_adjacent import ROOT, rank


def overdue_factors(draws: list[dict]) -> tuple[list[dict], dict[int, int]]:
    """Newest first; window-capped omissions, ties resolved by ascending ball."""
    counts = dict.fromkeys(range(1, 40), 0)
    windows = []
    for period in (6, 12, 18, 24, 30, 36, 42, 48):
        recent = draws[:period]
        if len(recent) < period:
            raise ValueError(f"不足 {period} 期開獎資料")
        ranking = []
        for number in counts:
            omission = next((i for i, draw in enumerate(recent) if number in draw["numbers"]), period)
            ranking.append(dict(number=number, omission=omission, atLeast=omission == period))
        ranking.sort(key=lambda item: (-item["omission"], item["number"]))
        top = ranking[:5]
        for item in top:
            counts[item["number"]] += 1
        windows.append(dict(period=period, top=top))
    return windows, counts


def next_draw_date(cutoff: str) -> str:
    target = date.fromisoformat(cutoff) + timedelta(days=1)
    while target.weekday() == 6:
        target += timedelta(days=1)
    return target.isoformat()


def main() -> None:
    payload = json.loads((ROOT / "docs/data/daily539.json").read_text(encoding="utf-8"))
    reference = json.loads(
        (ROOT / "docs/data/539-pilio-reference.json").read_text(encoding="utf-8")
    )
    if reference["source_date"] != payload["latest_draw_date"]:
        raise ValueError("來源截止日不同，保留先前合併頁，不混用不同日期。")
    ranking = rank(list(reversed(payload["draws"][:200])))
    overdue_windows, overdue_counts = overdue_factors(payload["draws"])
    for item in ranking:
        tags = [
            name for name, numbers in reference["categories"].items() if item["number"] in numbers
        ]
        item["tags"] = tags
        item["bonus"] = len(tags) / 10
        item["overdue_count"] = overdue_counts[item["number"]]
        item["overdue_bonus"] = item["overdue_count"] / 10
        item["combined"] = (round(item["score"] * 10) + len(tags) + item["overdue_count"]) / 10
    ranking.sort(key=lambda x: (-x["combined"], x["number"]))
    assert len({x["number"] for x in ranking}) == 39
    result = dict(
        latest_draw_no=payload["latest_draw_no"],
        date=payload["latest_draw_date"],
        reference=reference,
        ranking=ranking,
        overdue_windows=overdue_windows,
        overdue_weight=0.1,
        historical_backtest=False,
        target_date=next_draw_date(payload["latest_draw_date"]),
        target_note="下一個週一至週六開獎日的參考排名，實際開獎安排以官方公告為準；不是已開出的獎號。",
    )
    (ROOT / "docs/data/539-combined.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    source = (ROOT / "docs/539-adjacent-reference.html").read_text(encoding="utf-8")
    source = source.replace("今彩539｜相鄰次數39格", "今彩539｜相鄰分數＋AI快報")
    source = source.replace("今彩539 · 相鄰次數", "今彩539 · 合併參考排名")
    source = source.replace("相鄰次數，一列39個號碼", "合併參考分數，一列39個號碼")
    source = source.replace("次數在上 · 球號在下", "合計分在上 · 球號在下")
    source = source.replace("次數在上，球號在下", "合計分在上，球號在下")
    start = source.index('<div class="note">')
    end = source.index("</div>", start) + 6
    source = (
        source[:start]
        + """<div class="note">試作規則：相鄰分數＋Pilio四類提及各0.1分＋最久未開前5號入選次數×0.1分（最高0.8分）。上方為合計分，同分球號升序；每5格底色分組。</div>
<p>最久未開因素：近6／12／18／24／30／36／42／48期，各取未開期數最長的5號；最新一期開出為0期，區間內未開以該區間期數計。同值依球號小到大取前5號。八個重疊區間分別計次。相鄰、快報與未開因素截止日一致；尚無歷史快報逐日快照可作全歷史回測。</p>
<p><a href="https://www.pilio.idv.tw/lto539/sqlaibrief.asp" target="_blank" rel="noopener">Pilio AI快報來源</a> · <a href="data/539-combined.json">檢視逐號計分明細</a></p>
<details><summary>展開相鄰分數、快報加分、最久未開入選次數與加分</summary><div style="overflow-x:auto"><table style="width:100%;text-align:left;border-collapse:collapse"><thead><tr><th>排名</th><th>球號</th><th>相鄰分數</th><th>快報加分</th><th>未開入選次數</th><th>未開加分</th><th>合計</th><th>快報類別</th></tr></thead><tbody id="breakdown"></tbody></table></div></details>
<details><summary>展開八個區間最久未開前5號</summary><div id="overdue-windows"></div></details>"""
        + source[end:]
    )
    start = source.index("<script>")
    source = (
        source[:start]
        + """<script>
fetch('data/539-combined.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('讀取失敗');return r.json()}).then(p=>{
 document.getElementById('status').textContent=`參考目標：${p.target_date}（待開獎）｜資料截至 ${p.date} · 第${p.latest_draw_no}期｜AI快報截至 ${p.reference.source_date}`;
 document.getElementById('numbers').innerHTML=p.ranking.map(x=>`<div class="cell" aria-label="${x.number}號，合計${x.combined.toFixed(1)}分"><span class="count">${x.combined.toFixed(1)}分</span><span class="ball">${String(x.number).padStart(2,'0')}</span></div>`).join('');
 document.getElementById('breakdown').innerHTML=p.ranking.map((x,i)=>`<tr><td>${i+1}</td><td>${String(x.number).padStart(2,'0')}</td><td>${x.score.toFixed(1)}</td><td>${x.bonus.toFixed(1)}</td><td>${x.overdue_count}</td><td>${x.overdue_bonus.toFixed(1)}</td><td>${x.combined.toFixed(1)}</td><td>${x.tags.join('、')||'—'}</td></tr>`).join('');
 document.getElementById('overdue-windows').innerHTML=p.overdue_windows.map(w=>`<p>近 ${w.period} 期：${w.top.map(x=>`${String(x.number).padStart(2,'0')}（${x.atLeast?'至少 ':''}${x.omission} 期未開）`).join('、')}</p>`).join('');
}).catch(e=>{document.getElementById('status').textContent=e.message});
</script></body></html>"""
    )
    (ROOT / "docs/539-combined-reference.html").write_text(source, encoding="utf-8")
    print("Combined ranking:", " ".join(f"{x['number']:02}" for x in ranking))


if __name__ == "__main__":
    main()
