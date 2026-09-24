from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.api.draws import recent_daily539_draws
from app.core.database import Base, SessionLocal, engine
from app.core.paths import PROJECT_ROOT, ensure_directories
from app.services.bootstrap import initialize_catalog
from app.services.data_sources.official import _get, _update_taiwan
from app.services.bootstrap import load_json_yaml
from app.core.paths import CONFIG_DIR


OUTPUT_PATH = PROJECT_ROOT / "docs" / "data" / "daily539.json"
TAIPEI = ZoneInfo("Asia/Taipei")


def prepare_database() -> None:
    ensure_directories()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        initialize_catalog(db)


def update_taiwan_draws() -> None:
    """Only the current year is needed for 200 daily draws in the Pages export."""
    with SessionLocal() as db:
        _update_taiwan(db, first_year_override=datetime.now().year)


def export_payload() -> dict[str, object]:
    with SessionLocal() as db:
        payload = recent_daily539_draws(limit=200, db=db)
    sources = load_json_yaml(CONFIG_DIR / "sources.yaml")["taiwan"]
    month = datetime.now(TAIPEI).strftime("%Y-%m")
    response = _get(
        f"{str(sources['current_results_api']).rstrip('/')}/Daily539Result"
        f"?month={month}&endMonth={month}&pageNum=1&pageSize=500"
    )
    official_rows = (response.json().get("content") or {}).get("daily539Res") or []
    merged = {str(item["draw_no"]): item for item in payload["draws"]}
    for row in official_rows:
        draw_no = str(row["period"])
        merged[draw_no] = {
            "draw_no": draw_no,
            "draw_date": str(row["lotteryDate"]).split("T", 1)[0],
            "numbers": sorted(int(value) for value in row["drawNumberAppear"][:5]),
            "source_status": "official",
        }
    draws = sorted(
        merged.values(),
        key=lambda item: (str(item["draw_date"]), str(item["draw_no"])),
        reverse=True,
    )[:200]
    payload["draws"] = draws
    payload["draw_count"] = len(draws)
    payload["latest_draw_no"] = draws[0]["draw_no"]
    payload["latest_draw_date"] = draws[0]["draw_date"]
    payload["generated_at"] = datetime.now(TAIPEI).isoformat()
    payload["source"] = "台灣彩券官方資料"
    return payload


def main() -> int:
    print("[Numeris] Preparing the GitHub Pages dataset...")
    prepare_database()
    print("[Numeris] Downloading the latest Taiwan Lottery data...")
    update_taiwan_draws()
    payload = export_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[Numeris] Wrote {OUTPUT_PATH} with {payload['draw_count']} Daily 539 draws.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
