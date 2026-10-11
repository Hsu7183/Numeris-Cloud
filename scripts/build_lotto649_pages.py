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
        text = text.replace("今彩539", "大樂透").replace("今彩 539", "大樂透")
        text = text.replace("DAILY 539", "LOTTO 6/49")
        text = text.replace("daily539", "lotto649").replace("539", "649")
        text = text.replace("data/lotto649", "../data/lotto649")
        text = text.replace("lotto649.html?", "index.html?")
        text = text.replace('href="lotto649.html"', 'href="index.html"')
        text = text.replace("TW_DAILY649", "TW_LOTTO649")
        text = text.replace('href="daily649.html"', 'href="index.html"')
        text = text.replace("1–39", "1–49").replace("01–39", "01–49")
        text = re.sub(r"length:\s*39", "length: 49", text)
        text = text.replace("<= 39", "<= 49").replace(".repeat(39)", ".repeat(49)")
        text = text.replace('colspan="39"', 'colspan="49"').replace("repeat(39,", "repeat(49,")
        if name == "daily539_output.js":
            text = text.replace('rowspan="5"', 'rowspan="6"')
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
    text = re.sub(
        r'<a class="xlsx-output-link" href="period-grid.html">開啟 112 年期數格表</a>', "", text
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


if __name__ == "__main__":
    build()
