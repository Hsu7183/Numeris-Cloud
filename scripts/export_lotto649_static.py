"""Export 200 official Lotto 6/49 draws, keeping the special ball separate."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.paths import CONFIG_DIR, PROJECT_ROOT
from app.services.bootstrap import load_json_yaml
from app.services.data_sources.official import _get


def export_payload() -> dict[str, object]:
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    base = load_json_yaml(CONFIG_DIR / "sources.yaml")["taiwan"]["current_results_api"]
    # Two years cover 200 twice-weekly draws, including extra holiday draws.
    response = _get(
        f"{str(base).rstrip('/')}/Lotto649Result"
        f"?month={now.year - 2}-{now.month:02d}&endMonth={now:%Y-%m}"
        "&pageNum=1&pageSize=500"
    )
    rows = (response.json().get("content") or {}).get("lotto649Res") or []
    draws = []
    seen = set()
    for row in rows:
        values = [int(value) for value in row["drawNumberAppear"]]
        if len(values) != 7 or len(set(values)) != 7 or not all(1 <= n <= 49 for n in values):
            raise ValueError(f"Invalid official Lotto 6/49 draw: {row.get('period')}")
        number = str(row["period"])
        if number in seen:
            continue
        seen.add(number)
        draws.append(
            {
                "draw_no": number,
                "draw_date": str(row["lotteryDate"]).split("T", 1)[0],
                "numbers": sorted(values[:6]),
                "special_numbers": values[6:],
                "source_status": "official",
            }
        )
    draws.sort(key=lambda draw: (draw["draw_date"], draw["draw_no"]), reverse=True)
    draws = draws[:200]
    if len(draws) < 200:
        raise ValueError(f"Expected 200 official draws; received {len(draws)}")
    return {
        "game_code": "TW_LOTTO649",
        "game_name": "大樂透",
        "ball_count": 49,
        "main_number_count": 6,
        "draw_count": len(draws),
        "requested_limit": 200,
        "latest_draw_no": draws[0]["draw_no"],
        "latest_draw_date": draws[0]["draw_date"],
        "generated_at": now.isoformat(),
        "source": "台灣彩券官方資料",
        "draws": draws,
    }


def main() -> None:
    payload = export_payload()
    path = PROJECT_ROOT / "docs" / "data" / "lotto649.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {payload['draw_count']} Lotto draws; latest {payload['latest_draw_date']}")


if __name__ == "__main__":
    main()
