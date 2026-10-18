from copy import deepcopy
from datetime import date, timedelta

import pytest

from scripts import lotto649_modes as modes
from scripts.update_lotto649_aibrief import parse


def sample_history():
    return [
        dict(
            draw_no=str(115000001 + i),
            draw_date=(date(2026, 1, 1) + timedelta(days=i)).isoformat(),
            numbers=[1, 2, 3, 4, 48, 49] if i % 2 else [7, 8, 9, 10, 46, 47],
            special_numbers=[40],
            source_status="official",
        )
        for i in range(203)
    ]


@pytest.mark.parametrize(
    "ranker,method", [(modes.score_rank, "scores"), (modes.count_rank, "counts")]
)
def test_lotto_replay_excludes_special_and_future_draws(ranker, method):
    history = sample_history()
    result = modes.replay(history, ranker, method)
    assert result["trials"] == 3
    assert sum(x["hits"] for x in result["position_hits"]) == 18
    assert next(x["hits"] for x in result["ball_frequency"] if x["number"] == 40) == 0
    assert all(x["random_average"] == 6 * x["top"] / 49 for x in result["summary"])
    assert all(sum(x["distribution"].values()) == 3 for x in result["summary"])
    for trial in result["details"]:
        assert sorted(x["number"] for x in trial["ranking"]) == list(range(1, 50))
        assert trial["anchor_date"] < trial["target_date"]
    changed = deepcopy(history)
    changed[200]["numbers"] = [20, 21, 22, 23, 24, 25]
    changed[200]["special_numbers"] = [49]
    assert (
        modes.replay(changed, ranker, method)["details"][0]["ranking"]
        == result["details"][0]["ranking"]
    )


def test_lotto_snapshot_survives_without_database(tmp_path, monkeypatch):
    monkeypatch.setattr(modes, "ROOT", tmp_path)
    history = sample_history()
    modes.write_json(tmp_path / "reports/649-adjacent-source.json", history)
    modes.write_json(
        tmp_path / "docs/data/lotto649.json",
        dict(draws=history[-2:][::-1], latest_draw_no=history[-1]["draw_no"]),
    )
    assert len(modes.load_history()) == 203
    assert modes.load_history()[0]["draw_no"] == history[0]["draw_no"]


def test_lotto_brief_supports_high_balls_without_reading_percentages():
    content = (
        '<p>開獎更新日期:2026/10/16</p><div class="ai-brief">'
        + "資料說明。" * 30
        + "49號與48號，3和4號，機率16.38%，20期。50號並非有效球號。</div>"
    )
    result = parse(content)
    assert result["mentioned_numbers"] == [3, 4, 48, 49]
