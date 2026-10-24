"""Build the 49-ball counterpart from the existing Daily 539 Pages layouts."""

# ruff: noqa: E501 -- embedded HTML/JS replacements preserve the source layouts.
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs"


def build() -> None:
    target = ROOT / "lotto649"
    target.mkdir(exist_ok=True)
    names = [
        "app.js",
        "styles.css",
        "output.html",
        "period-grid.html",
        "pattern-grid.html",
        "pattern-template.html",
        "excel-539-grid.html",
        "handwritten-539-grid.html",
        "handwritten-539-overlay.html",
        "539-adjacent-reference.html",
        "539-aibrief.js",
        "539-aibrief.css",
        "539-hit-ranking.css",
        "539-overdue.js",
    ]
    names += [p.name for p in ROOT.glob("daily539_*")]
    names += [p.name for p in ROOT.glob("excel-539-*") if p.suffix in {".js", ".css"}]
    names += ["handwritten-539-grid.js", "handwritten-539-grid.css", "handwritten-539-overlay.js"]
    for name in names:
        text = (ROOT / name).read_text(encoding="utf-8")
        # Historical manually mapped 539 fixtures must never enter Lotto statistics.
        if name == "app.js":
            text = re.sub(
                r"const officialDraws = \{.*?\n  \};", "const officialDraws = {};", text, flags=re.S
            )
        if name == "handwritten-539-grid.js":
            start = text.index("  const defaultAdjacentGroups")
            end = text.index("  const renderNumberGrid")
            text = (
                text[:start]
                + "  const officialDraws = {};\n  const officialMappedPositions = {};\n  const officialAdjacentGroups = {};\n"
                + text[end:]
            )
            text = text.replace(
                '      if (!adjacentGroups && draw.draw_date === "2026-09-25") adjacentGroups = defaultAdjacentGroups;\n',
                "",
            )
            text = text.replace(
                "adjacentGroups = defaultAdjacentGroups;",
                "throw new Error('相鄰統計計算失敗，請重新整理');",
            )
            text = text.replace("length: 20", "length: 49")
        if name == "excel-539-diagram.js":
            text = re.sub(
                r"const exactPositions = \{.*?\n  \};",
                "const exactPositions = {};",
                text,
                flags=re.S,
            )
            text = re.sub(
                r"const fallbackAdjacentGroups = \[.*?\n  \];",
                "const fallbackAdjacentGroups = [];",
                text,
                flags=re.S,
            )
            text = text.replace(
                "adjacentGroups = fallbackAdjacentGroups;",
                "throw new Error('相鄰統計計算失敗，請重新整理');",
            )
            text = text.replace("length: 20", "length: 49")
        if name == "handwritten-539-overlay.js":
            text = text.replace("length: 20", "length: 49")
            text = text.replace("const columnCount = 20;", "const columnCount = 49;")
        text = text.replace("今彩539", "大樂透").replace("今彩 539", "大樂透")
        text = text.replace("DAILY 539", "LOTTO 6/49")
        text = text.replace("daily539", "lotto649").replace("539", "649")
        text = text.replace("data/lotto649", "../data/lotto649")
        text = text.replace("data/649-", "../data/649-")
        text = text.replace("/lto649/", "/ltobig/")
        text = text.replace("lotto649.html?", "index.html?")
        text = text.replace('href="lotto649.html"', 'href="index.html"')
        text = text.replace("TW_DAILY649", "TW_LOTTO649")
        text = text.replace('href="daily649.html"', 'href="index.html"')
        text = text.replace("1–39", "1–49").replace("01–39", "01–49")
        text = re.sub(r"length:\s*39", "length: 49", text)
        text = text.replace("<= 39", "<= 49").replace(".repeat(39)", ".repeat(49)")
        text = text.replace('colspan="39"', 'colspan="49"').replace("repeat(39,", "repeat(49,")
        text = text.replace("39個", "49個").replace("39格", "49格")
        text = text.replace("39號", "49號").replace("/ 39", "/ 49")
        text = text.replace("n > 39", "n > 49")
        if name == "539-adjacent-reference.html":
            text = text.replace("Array(40)", "Array(50)")
            text = text.replace("!== 5", "!== 6")
            text = text.replace(
                "</style>",
                ".row .cell:nth-child(n+41):nth-child(-n+45){background:#e1edf0}.row .cell:nth-child(n+46){background:#f7e7d4}</style>",
                1,
            )
            text = text.replace("每天22:00更新資料。", "依已載入的官方主號資料計算；特別號另列。")
        if name == "539-hit-ranking.css":
            text += "\n.compact-hit-ranking .hit-group-8{--group-color:#64748b}.compact-hit-ranking .hit-group-9{--group-color:#b45309}\n"
        if name == "daily539_output.js":
            text = text.replace('rowspan="5"', 'rowspan="6"')
            text = text.replace("顯示 5 顆球", "顯示 6 顆主球（特別號不計）")
            text = text.replace("/649/pages/../data/lotto649.json", "../data/lotto649.json")
        if name == "excel-539-grid.js":
            text = text.replace("[[1, 13], [14, 26], [27, 39]]", "[[1, 17], [18, 33], [34, 49]]")
            text = text.replace("length: 5", "length: 6").replace("五個", "六個")
        if name == "daily539_pattern_grid.js":
            text = re.sub(
                r"const topHeaders = .*?;",
                "const topHeaders = Array.from({length: 10}, (_, i) => Array.from({length: 49}, (_, n) => n + 1).filter(n => n % 10 === i));",
                text,
            )
            text = re.sub(
                r"const bottomHeaders = .*?;",
                "const bottomHeaders = Array.from({length: 4}, (_, i) => Array.from({length: 49}, (_, n) => n + 1).filter(n => (n - 1) % 4 === i));",
                text,
            )
            text = re.sub(
                r"document.querySelector\(\"#pattern-status\"\).textContent = `.*?`;",
                'document.querySelector("#pattern-status").textContent = `已填入近 ${draws.length} 期，主號 01–49；同號累計出現次數依序標示。`;',
                text,
            )
        if name == "daily539_pattern_template.js":
            text = text.replace(
                "(payload.draws || []).slice().reverse()",
                "(payload.draws || []).slice(0, 27).reverse()",
            )
            text = text.replace("第 12 行最新", "第 27 行最新")
        if name == "daily539_period_grid.js":
            text = text.replace(
                'const payload = JSON.parse(localStorage.getItem("lotto649OutputData") || "null");',
                'const response = await fetch("../data/lotto649.json", {cache:"no-store"});\n      if (!response.ok) throw new Error("期數資料讀取失敗");\n      const payload = await response.json();',
            )
            start = text.index("    const response = await fetch(`/api/draws?")
            end = text.index("    const markerDraws =", start)
            text = (
                text[:start]
                + """    const response = await fetch("649-full-audit.json", {cache:"no-store"});
    if (!response.ok) throw new Error("歷史資料讀取失敗");
    const all = await response.json();
    const draws = all.filter(d => d.draw_date <= dateTo).reverse().slice(0, 200);
"""
                + text[end:]
            )
            text = text.replace(
                'markerName: "112/06/26–112/07/18"', "markerName: `${dateFrom}～${dateTo}`"
            )
            text = text.replace(
                "const groups = frequencyGroups(draws, period);",
                "const groups = frequencyGroups(draws, period);\n    columns = Math.max(columns, ...[...groups.values()].map(values => values.length));\n    const maxCount = Math.max(42, ...groups.keys());",
            )
            text = text.replace("length: 43", "length: maxCount + 1").replace(
                "42 - rowIndex", "maxCount - rowIndex"
            )
            text = text.replace("共 43 行", "共 ${maxCount + 1} 行")
        if name == "styles.css":
            text += "\nbody { overflow:auto; } .page-shell { height:auto; min-height:100vh; } .frequency-group>div { flex-wrap:wrap; row-gap:2px; } .output-actions { flex-wrap:wrap; } .result-header { flex-wrap:wrap; gap:8px; }\n"
        if name.endswith(".html"):
            text = text.replace('href="./"', 'href="index.html"')
            text = text.replace("01–20", "01–49").replace("1–20", "1–49")
            if 'name="viewport"' not in text:
                text = text.replace(
                    "<head>",
                    '<head><meta name="viewport" content="width=device-width, initial-scale=1">',
                )
        if name == "daily539_output.css":
            text += "\n.matrix-wrap { overflow-x:auto; } .matrix-wrap table { min-width:1100px; } .matrix-col { width:1.81%; } tbody tr:nth-child(5n) td,tbody tr:nth-child(5n) th { border-bottom:1px solid var(--grid); } tbody tr:nth-child(6n) td,tbody tr:nth-child(6n) th { border-bottom:2px solid #5b876e; }\n"
        if name == "daily539_pattern_template.css":
            text += "\n.month-grid { overflow-x:auto; } .month-grid table { min-width:1100px; }\n"
        if name == "handwritten-539-grid.css":
            text += "\n.number-sheet { overflow-x:auto; } .number-sheet table, .draw-sheet table { min-width:1500px; } .sheet-layout { grid-template-columns:1fr; }\n"
        if name == "excel-539-diagram.css":
            text += "\n.number-board, .adjacent-table-wrap { overflow-x:auto; } .number-board table, .adjacent-table { min-width:1500px; } .diagram-content { display:block; }\n"
        if name == "handwritten-539-overlay.html":
            text = text.replace("39球號命中統計", "49球號命中統計")
            text = text.replace(
                "</main>",
                '<section data-aibrief aria-live="polite"><h2>AI快報 · 球號比對</h2></section></main>',
            )
            text = text.replace("</body>", '<script src="649-aibrief.js"></script></body>')
            text = text.replace("</head>", '<link rel="stylesheet" href="649-aibrief.css"></head>')
        if name == "handwritten-539-grid.js":
            text = text.replace("6／12／18／24／30期疊加", "6／12／18／24／30／36／42／48期疊加")
        if name == "daily539_pattern_template.html":
            text = text.replace("39 號", "49 號")
        if name == "handwritten-539-overlay.html":
            text = text.replace(
                "</style>", ".overlay-panel table,.adjacent-overlay table{min-width:1500px}</style>"
            )
        (target / name.replace("daily539", "lotto649").replace("539", "649")).write_text(
            text, encoding="utf-8"
        )
    text = (ROOT / "daily539.html").read_text(encoding="utf-8")
    text = (
        text.replace("今彩539", "大樂透").replace("DAILY 539", "LOTTO 6/49").replace("1–39", "1–49")
    )
    text = text.replace("539", "649").replace('href="index.html"', 'href="../index.html"')
    text = text.replace("次數39格", "次數49格")
    # Keep the main navigation visible before data finishes loading.
    text = text.replace(
        "</nav>",
        '<a class="xlsx-output-link" href="handwritten-649-overlay.html">12．期數疊加</a><a class="xlsx-output-link" href="649-top5-hit-ranking.html">13．49球號命中統計</a><a class="xlsx-output-link" href="649-dashboard.html">14．完整總覽與資料查核</a></nav>',
        1,
    )
    text = text.replace(
        'href="period-grid.html">07．',
        'href="period-grid.html?from=2023-06-26&amp;to=2023-07-18">07．',
    )
    text = text.replace("出現次數與期次順序。", "出現次數與期次順序（僅計 6 個主號，特別號另列）。")
    (target / "index.html").write_text(text, encoding="utf-8")
    app = target / "app.js"
    text = app.read_text(encoding="utf-8")
    text = text.replace(
        "const latestNumbers = payload.draws[0].numbers;",
        "const latestNumbers = payload.draws[0].numbers;",
    )
    text = text.replace(
        "${payload.latest_draw_date}`;",
        "${payload.latest_draw_date} · 主號 ${latestNumbers.join('、')} · 特別號 ${(payload.draws[0].special_numbers || []).join('、') || '—'}`;",
        1,
    )
    app.write_text(text, encoding="utf-8")
    from scripts.lotto649_modes import build as build_modes

    build_modes()


if __name__ == "__main__":
    build()
