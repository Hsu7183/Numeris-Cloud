from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_games_draws_and_analytics() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        games = client.get("/api/games")
        assert games.status_code == 200
        assert len(games.json()) == 9
        draws = client.get("/api/draws", params={"game_code": "TW_LOTTO649"})
        assert draws.status_code == 200
        assert draws.json()["total"] >= 30
        frequency = client.get(
            "/api/analytics/frequency",
            params={"game_code": "TW_LOTTO649", "lookback_count": 20},
        )
        assert frequency.status_code == 200
        assert frequency.json()["actual_lookback"] == 20


def test_generation_reproducibility_lock_and_exports() -> None:
    payload = {
        "game_code": "TW_LOTTO649",
        "ticket_count": 10,
        "lookback_count": 20,
        "random_seed": 777,
        "max_overlap": 3,
    }
    with TestClient(app) as client:
        first = client.post("/api/generation/run", json=payload)
        second = client.post("/api/generation/run", json=payload)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        first_tickets = [item["pools"] for item in first.json()["tickets"]]
        second_tickets = [item["pools"] for item in second.json()["tickets"]]
        assert first_tickets == second_tickets
        assert all(len(item["main"]) == 6 for item in first_tickets)
        assert all("special" not in item for item in first_tickets)
        run_uuid = first.json()["run_uuid"]
        locked = client.post(f"/api/generation/runs/{run_uuid}/lock")
        assert locked.status_code == 200
        assert locked.json()["locked"] is True
        csv_export = client.get(f"/api/exports/generation/{run_uuid}.csv")
        json_export = client.get(f"/api/exports/generation/{run_uuid}.json")
        assert csv_export.status_code == 200
        assert csv_export.content.startswith(b"\xef\xbb\xbf")
        assert json_export.status_code == 200


def test_multi_pool_ordered_and_bingo_generation() -> None:
    cases = [
        ("TW_SUPER_LOTTO638", {"first": 6, "second": 1}),
        ("TW_PICK3", {"digits": 3}),
        ("TW_PICK4", {"digits": 4}),
        ("TW_BINGO", {"main": 6}),
        ("HK_MARKSIX", {"main": 6}),
        ("TW_DAILY539", {"main": 5}),
    ]
    with TestClient(app) as client:
        for index, (game_code, expected) in enumerate(cases):
            response = client.post(
                "/api/generation/run",
                json={
                    "game_code": game_code,
                    "ticket_count": 5,
                    "lookback_count": 20,
                    "random_seed": 100 + index,
                    "star_count": 6,
                },
            )
            assert response.status_code == 200, response.text
            for ticket in response.json()["tickets"]:
                for pool_code, count in expected.items():
                    assert len(ticket["pools"][pool_code]) == count


def test_consistent_error_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/games/NOT_A_GAME")
        assert response.status_code == 400
        payload = response.json()
        assert set(payload) == {"error_code", "message", "detail", "request_id"}
        assert payload["message"] == "找不到指定彩種"
