from __future__ import annotations

from scripts.startup_refresh import (
    active_game_codes,
    refresh_weekly_recommendations,
)


def test_startup_refresh_prepares_one_weekly_recommendation_for_every_active_game() -> None:
    active_codes = active_game_codes()
    results = refresh_weekly_recommendations()

    assert "TW_BINGO" not in active_codes
    assert {item["game_code"] for item in results} == set(active_codes)
    assert all(item["status"] == "ready" for item in results)
    assert all(item["weekly_key"] for item in results)
    assert all(item["recommendation_anchor"] for item in results)
    assert all(item["numbers"] for item in results)
