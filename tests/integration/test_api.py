from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.main import app
from app.models.database_models import GenerationRun


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


def test_simple_dashboard_single_wheel_and_weekly_evaluation() -> None:
    with TestClient(app) as client:
        single = client.post(
            "/api/simple/generate",
            json={
                "game_code": "HK_MARKSIX",
                "mode": "single",
                "ticket_count": 10,
                "random_seed": 88001,
                "refresh": True,
            },
        )
        assert single.status_code == 200, single.text
        assert single.json()["locked"] is True
        assert single.json()["generated_ticket_count"] == 10

        wheel = client.post(
            "/api/simple/generate",
            json={
                "game_code": "HK_MARKSIX",
                "mode": "wheel7",
                "random_seed": 88002,
                "refresh": True,
            },
        )
        assert wheel.status_code == 200, wheel.text
        wheel_payload = wheel.json()
        assert wheel_payload["generated_ticket_count"] == 7
        wheel_numbers = set(wheel_payload["config"]["wheel_numbers"])
        assert len(wheel_numbers) == 7
        assert all(
            set(ticket["pools"]["main"]).issubset(wheel_numbers)
            for ticket in wheel_payload["tickets"]
        )

        with SessionLocal() as db:
            run = db.scalar(
                select(GenerationRun).where(
                    GenerationRun.run_uuid == single.json()["run_uuid"]
                )
            )
            assert run is not None
            run.target_draw_no = "F0060"
            db.commit()
        evaluated = client.post(
            f"/api/generation/runs/{single.json()['run_uuid']}/evaluate",
            params={"actual_draw_no": "F0060"},
        )
        assert evaluated.status_code == 200, evaluated.text
        dashboard = client.get("/api/simple/dashboard/HK_MARKSIX")
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload["game"]["wheel_modes"] == [7, 8, 9]
        assert payload["records"]
        assert payload["weekly_performance"]
        recent_period = next(
            item for item in payload["recent_periods"] if item["draw_no"] == "F0060"
        )
        assert len(recent_period["predicted_numbers"]) == 6
        assert len(recent_period["actual_numbers"]) == 6
        assert len(recent_period["actual_special_numbers"]) == 1
        assert recent_period["comparison_number_count"] == 6
        assert recent_period["comparison_hit_rate"] is not None
        recent_summary = payload["performance_summary"]["recent_10"]
        assert recent_summary["tickets"] > 0
        assert recent_summary["number_accuracy"] == round(
            recent_summary["hit_numbers"]
            / recent_summary["checked_numbers"]
            * 100,
            2,
        )
        assert recent_summary["any_hit_ticket_rate"] == round(
            recent_summary["tickets_with_hit"]
            / recent_summary["tickets"]
            * 100,
            2,
        )
        assert payload["performance_summary"]["latest_week"]["ticket_hit_rate"] is not None
        assert (
            payload["performance_summary"]["latest_week"]["any_hit_ticket_rate"]
            == payload["performance_summary"]["latest_week"]["ticket_hit_rate"]
        )
        assert payload["performance_summary"]["overall"]["number_accuracy"] is not None
        assert "10組單式" in payload["metric_definitions"]["number_accuracy"]
        assert "逐期表第1組" in payload["metric_definitions"]["period_comparison"]
        assert "不是未來中獎機率" in payload["metric_note"]


def test_simple_dashboard_uses_official_history_when_available() -> None:
    with TestClient(app) as client:
        dashboard = client.get("/api/simple/dashboard/TW_LOTTO649")
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload["data"]["official_count"] > 0
        assert payload["data"]["fixture_count"] == 0
        assert payload["records"]


def test_consistent_error_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/games/NOT_A_GAME")
        assert response.status_code == 400
        payload = response.json()
        assert set(payload) == {"error_code", "message", "detail", "request_id"}
        assert payload["message"] == "找不到指定彩種"
