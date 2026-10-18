"""Build a reviewable current snapshot combining adjacency scores and brief mentions."""

# ruff: noqa: E501 -- literal standalone page markup and JavaScript.

from __future__ import annotations

import json

from scripts.backtest_539_adjacent import ROOT, rank


def main() -> None:
    payload = json.loads((ROOT / "docs/data/daily539.json").read_text(encoding="utf-8"))
    reference = json.loads(
        (ROOT / "docs/data/539-pilio-reference.json").read_text(encoding="utf-8")
    )
    if reference["source_date"] != payload["latest_draw_date"]:
        raise ValueError("來源截止日不同，保留先前合併頁，不混用不同日期。")
    ranking = rank(list(reversed(payload["draws"][:200])))
    for item in ranking:
        tags = [
            name for name, numbers in reference["categories"].items() if item["number"] in numbers
        ]
        item["tags"] = tags
        item["bonus"] = len(tags) / 10
        item["combined"] = (round(item["score"] * 10) + len(tags)) / 10
    ranking.sort(key=lambda x: (-x["combined"], x["number"]))
    assert len({x["number"] for x in ranking}) == 39
    result = dict(
        latest_draw_no=payload["latest_draw_no"],
        date=payload["latest_draw_date"],
        reference=reference,
        ranking=ranking,
        historical_backtest=False,
    )
    (ROOT / "docs/data/539-combined.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    source = (ROOT / "docs/539-adjacent-reference.html").read_text(encoding="utf-8")
    source = source.replace("今彩539｜相鄰次數39格", "今彩539｜相鄰分數＋AI快報")
    source = source.replace("今彩539 · 相鄰次數", "今彩539 · 合併參考排名")
    source = source.replace("相鄰次數，一列39個號碼", "合併參考分數，一列39個號碼")
    source = source.replace("次數在上 · 球號在下", "合計分在上 · 球號在下")
    start = source.index('<div class="note">')
    end = source.index("</div>", start) + 6
    source = (
        source[:start]
        + """<div class="note">試作規則：output.html相鄰分數＋Pilio四類提及各0.1分。上方為合計分，同分球號升序；每5格底色分組。</div>
<p>相鄰分數與快報截止日一致。冷門、未開期數及條件拖牌不加減分。此為目前資料的合併參考，尚無歷史快報逐日快照可作全歷史回測。</p>
<p><a href="https://www.pilio.idv.tw/lto539/sqlaibrief.asp" target="_blank" rel="noopener">Pilio AI快報來源</a> · <a href="data/539-combined.json">檢視逐號計分明細</a></p>
<details><summary>展開相鄰分數、快報加分與提及類別</summary><table style="width:100%;text-align:left;border-collapse:collapse"><thead><tr><th>排名</th><th>球號</th><th>相鄰分數</th><th>快報加分</th><th>合計</th><th>類別</th></tr></thead><tbody id="breakdown"></tbody></table></details>"""
        + source[end:]
    )
    start = source.index("<script>")
    source = (
        source[:start]
        + """<script>
fetch('data/539-combined.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('讀取失敗');return r.json()}).then(p=>{
 document.getElementById('status').textContent=`截止 ${p.date} · 第${p.latest_draw_no}期 · 相鄰分數＋AI快報試作加權`;
 document.getElementById('numbers').innerHTML=p.ranking.map(x=>`<div class="cell" aria-label="${x.number}號，合計${x.combined.toFixed(1)}分"><span class="count">${x.combined.toFixed(1)}分</span><span class="ball">${String(x.number).padStart(2,'0')}</span></div>`).join('');
 document.getElementById('breakdown').innerHTML=p.ranking.map((x,i)=>`<tr><td>${i+1}</td><td>${String(x.number).padStart(2,'0')}</td><td>${x.score.toFixed(1)}</td><td>${x.bonus.toFixed(1)}</td><td>${x.combined.toFixed(1)}</td><td>${x.tags.join('、')||'—'}</td></tr>`).join('');
}).catch(e=>{document.getElementById('status').textContent=e.message});
</script></body></html>"""
    )
    (ROOT / "docs/539-combined-reference.html").write_text(source, encoding="utf-8")
    print("Combined ranking:", " ".join(f"{x['number']:02}" for x in ranking))


if __name__ == "__main__":
    main()
