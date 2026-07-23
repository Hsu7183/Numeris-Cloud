from __future__ import annotations

import json
import sys
import time

import httpx

from app.core.paths import REPORT_DIR

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8767"


def post(path: str, payload: dict[str, object]) -> dict[str, object]:
    response = httpx.post(f"{BASE_URL}{path}", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def main() -> None:
    output_dir = REPORT_DIR / "build"
    output_dir.mkdir(parents=True, exist_ok=True)
    health = httpx.get(f"{BASE_URL}/api/health", timeout=15).json()
    lotto = post(
        "/api/generation/run",
        {
            "game_code": "TW_LOTTO649",
            "ticket_count": 10,
            "lookback_count": 20,
            "random_seed": 6492026,
            "max_overlap": 3,
        },
    )
    lotto_repeat = post(
        "/api/generation/run",
        {
            "game_code": "TW_LOTTO649",
            "ticket_count": 10,
            "lookback_count": 20,
            "random_seed": 6492026,
            "max_overlap": 3,
        },
    )
    super_lotto = post(
        "/api/generation/run",
        {
            "game_code": "TW_SUPER_LOTTO638",
            "ticket_count": 10,
            "lookback_count": 20,
            "random_seed": 6382026,
            "max_overlap": 3,
        },
    )
    pick3 = post(
        "/api/generation/run",
        {
            "game_code": "TW_PICK3",
            "ticket_count": 100,
            "lookback_count": 20,
            "random_seed": 3052026,
            "max_overlap": 2,
        },
    )
    daily539 = post(
        "/api/generation/run",
        {
            "game_code": "TW_DAILY539",
            "ticket_count": 10,
            "lookback_count": 20,
            "random_seed": 5392026,
            "max_overlap": 3,
        },
    )
    marksix = post(
        "/api/generation/run",
        {
            "game_code": "HK_MARKSIX",
            "ticket_count": 10,
            "lookback_count": 20,
            "random_seed": 4962026,
            "max_overlap": 3,
        },
    )
    pick4 = post(
        "/api/generation/run",
        {
            "game_code": "TW_PICK4",
            "ticket_count": 100,
            "lookback_count": 20,
            "random_seed": 4052026,
            "max_overlap": 3,
        },
    )
    bingo = post(
        "/api/generation/run",
        {
            "game_code": "TW_BINGO",
            "ticket_count": 10,
            "lookback_count": 20,
            "random_seed": 802026,
            "max_overlap": 5,
            "star_count": 10,
        },
    )
    leading_zero = any(ticket["pools"]["digits"][0] == 0 for ticket in pick3["tickets"])
    if not leading_zero:
        raise RuntimeError("3星彩驗收未產生前導0組合")
    pick4_leading_zero = any(ticket["pools"]["digits"][0] == 0 for ticket in pick4["tickets"])
    if not pick4_leading_zero:
        raise RuntimeError("4星彩驗收未產生前導0組合")
    replay = post(
        "/api/replay/run",
        {
            "game_code": "TW_LOTTO649",
            "start_index": 20,
            "end_index": 39,
            "lookback_count": 20,
            "tickets_per_draw": 5,
            "random_seed": 20260723,
            "baseline_repetitions": 20,
        },
    )
    for _ in range(180):
        replay_status = httpx.get(f"{BASE_URL}/api/replay/{replay['run_uuid']}", timeout=30).json()
        if replay_status["status"] not in {"pending", "running"}:
            break
        time.sleep(1)
    else:
        raise RuntimeError("歷史逐期模擬驗收逾時")
    if replay_status["status"] != "completed":
        raise RuntimeError(f"歷史逐期模擬失敗：{replay_status}")

    csv_response = httpx.get(
        f"{BASE_URL}/api/exports/generation/{lotto['run_uuid']}.csv", timeout=30
    )
    csv_response.raise_for_status()
    (output_dir / "acceptance_lotto.csv").write_bytes(csv_response.content)
    json_response = httpx.get(
        f"{BASE_URL}/api/exports/generation/{lotto['run_uuid']}.json", timeout=30
    )
    json_response.raise_for_status()
    (output_dir / "acceptance_lotto.json").write_bytes(json_response.content)

    result = {
        "health": health,
        "lotto": {
            "run_uuid": lotto["run_uuid"],
            "tickets": lotto["generated_ticket_count"],
            "valid": all(len(ticket["pools"]["main"]) == 6 for ticket in lotto["tickets"]),
            "has_extra_special_pick": any(
                "special" in ticket["pools"] for ticket in lotto["tickets"]
            ),
            "same_seed_reproduced": [ticket["pools"] for ticket in lotto["tickets"]]
            == [ticket["pools"] for ticket in lotto_repeat["tickets"]],
        },
        "super_lotto": {
            "run_uuid": super_lotto["run_uuid"],
            "tickets": super_lotto["generated_ticket_count"],
            "valid_6_plus_1": all(
                len(ticket["pools"]["first"]) == 6 and len(ticket["pools"]["second"]) == 1
                for ticket in super_lotto["tickets"]
            ),
        },
        "pick3": {
            "run_uuid": pick3["run_uuid"],
            "leading_zero": leading_zero,
        },
        "daily539": {
            "run_uuid": daily539["run_uuid"],
            "valid": all(
                len(ticket["pools"]["main"]) == 5
                and len(set(ticket["pools"]["main"])) == 5
                for ticket in daily539["tickets"]
            ),
        },
        "marksix": {
            "run_uuid": marksix["run_uuid"],
            "valid": all(
                len(ticket["pools"]["main"]) == 6
                and len(set(ticket["pools"]["main"])) == 6
                and "special" not in ticket["pools"]
                for ticket in marksix["tickets"]
            ),
        },
        "pick4": {
            "run_uuid": pick4["run_uuid"],
            "leading_zero": pick4_leading_zero,
            "ordered_digits": all(
                len(ticket["pools"]["digits"]) == 4 for ticket in pick4["tickets"]
            ),
        },
        "bingo": {
            "run_uuid": bingo["run_uuid"],
            "valid_10_star": all(
                len(ticket["pools"]["main"]) == 10
                and len(set(ticket["pools"]["main"])) == 10
                for ticket in bingo["tickets"]
            ),
        },
        "replay": replay_status,
        "exports": ["acceptance_lotto.csv", "acceptance_lotto.json"],
    }
    result_path = output_dir / "acceptance_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
