"""Export the latest 420 verified 539 draws for the workbench."""
from __future__ import annotations

import json

from app.core.paths import PROJECT_ROOT


def main() -> None:
    docs = PROJECT_ROOT / "docs"
    report = json.loads((docs / "539-adjacent-backtest.json").read_text(encoding="utf-8"))
    snapshot = json.loads((docs / "data/daily539.json").read_text(encoding="utf-8-sig"))
    draws = [
        {"draw_no": row["target_draw_no"], "draw_date": row["target_date"], "numbers": row["actual"]}
        for row in reversed(report["details"][-420:])
    ]
    if len(draws) != 420 or len({row["draw_no"] for row in draws}) != 420:
        raise ValueError("Expected 420 distinct verified draws")
    for calculated, official in zip(draws, snapshot["draws"], strict=False):
        if any(calculated[key] != official[key] for key in calculated):
            raise ValueError(f"Official snapshot disagrees for {official['draw_no']}")
    (docs / "data/539-workbench.json").write_text(
        json.dumps({"draws": draws}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
