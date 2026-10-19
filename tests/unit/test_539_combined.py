import json
import subprocess

import pytest

from scripts.backtest_539_adjacent import ROOT
from scripts.build_539_combined import overdue_factors


def test_overdue_matches_browser_and_counts_all_windows():
    draws = json.loads((ROOT / "docs/data/daily539.json").read_text(encoding="utf-8"))["draws"]
    windows, counts = overdue_factors(draws)
    script = (
        "require('./docs/539-overdue.js');"
        "const p=require('./docs/data/daily539.json');"
        "console.log(JSON.stringify(daily539Overdue.analyze(p.draws)));"
    )
    browser = json.loads(subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True))
    assert windows == browser["windows"]
    assert counts == {item["number"]: item["count"] for item in browser["factors"]}
    assert sum(counts.values()) == 40


def test_overdue_ties_and_insufficient_history():
    draws = [{"numbers": [1, 2, 3, 4, 5]}] * 48
    windows, counts = overdue_factors(draws)
    assert all([item["number"] for item in w["top"]] == [6, 7, 8, 9, 10] for w in windows)
    assert counts[6] == 8
    assert counts[1] == 0
    with pytest.raises(ValueError, match="不足 48"):
        overdue_factors(draws[:47])


def test_combined_snapshot_formula_and_sort():
    payload = json.loads((ROOT / "docs/data/539-combined.json").read_text(encoding="utf-8"))
    ranking = payload["ranking"]
    assert len({item["number"] for item in ranking}) == 39
    assert ranking == sorted(ranking, key=lambda item: (-item["combined"], item["number"]))
    for item in ranking:
        assert item["overdue_bonus"] == item["overdue_count"] / 10
        assert item["combined"] == (
            round(item["score"] * 10) + len(item["tags"]) + item["overdue_count"]
        ) / 10
