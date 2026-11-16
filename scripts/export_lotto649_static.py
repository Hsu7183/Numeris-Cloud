"""Export recent and historical official Lotto 6/49 draws."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from app.core.paths import CONFIG_DIR, PROJECT_ROOT
from app.services.bootstrap import load_json_yaml
from app.services.data_sources.official import _get, _parse_taiwan_annual_zip


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


def archive_draws(year: int, sources: dict) -> list[dict]:
    download_api = sources["annual_download_api"]
    response = _get(f"{download_api}?year={year}").json()
    url = (response.get("content") or {}).get("path") or ""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in sources["official_domains"] or not parsed.path.endswith(".zip"):
        raise ValueError(f"Missing official Lotto archive for {year}")
    return parse_archive(_get(url).content)


def parse_archive(content: bytes) -> list[dict]:
    rows, _ = _parse_taiwan_annual_zip(content)
    return [
        {
            "draw_no": row["draw_no"],
            "draw_date": datetime.strptime(row["draw_date"].replace("/", "-"), "%Y-%m-%d").date().isoformat(),
            "numbers": sorted(row["numbers"]),
            "special_numbers": [row["special_number"]],
            "source_status": "official",
        }
        for row in rows
        if row["game_code"] == "TW_LOTTO649"
    ]


def export_history(recent: list[dict], path: Path) -> list[dict]:
    sources = load_json_yaml(CONFIG_DIR / "sources.yaml")["taiwan"]
    first_year = int(sources["annual_first_year"])
    cached = json.loads(path.read_text(encoding="utf-8"))["draws"] if path.exists() else []
    years: dict[int, dict[str, dict]] = defaultdict(dict)
    for row in [*cached, *recent]:
        years[int(row["draw_date"][:4])][row["draw_no"]] = row

    latest_year = max(years)
    for year in range(first_year, latest_year + 1):
        rows = years[year]
        periods = {int(period[-6:]) for period in rows}
        if not periods or periods != set(range(1, max(periods) + 1)):
            # The official archive can fill years outside the recent API's range.
            for row in archive_draws(year, sources):
                if int(row["draw_date"][:4]) != year:
                    raise ValueError(f"Unexpected Lotto date in {year} archive")
                rows.setdefault(row["draw_no"], row)
            periods = {int(period[-6:]) for period in rows}
        if not periods or periods != set(range(1, max(periods) + 1)):
            raise ValueError(f"Missing official Lotto periods in {year}")
        for row in rows.values():
            period = row["draw_no"]
            values = [*row["numbers"], *row["special_numbers"]]
            if (
                len(period) not in {8, 9}
                or not period.isascii()
                or not period.isdecimal()
                or int(period[:-6]) != year - 1911
                or date.fromisoformat(row["draw_date"]).year != year
                or len(row["numbers"]) != 6
                or len(row["special_numbers"]) != 1
                or len(set(values)) != 7
                or any(type(value) is not int or not 1 <= value <= 49 for value in values)
            ):
                raise ValueError(f"Invalid official Lotto history draw: {period}")

    return sorted(
        (row for rows in years.values() for row in rows.values()),
        key=lambda row: (row["draw_date"], row["draw_no"]),
        reverse=True,
    )


def write_history(path: Path, draws: list[dict]) -> None:
    content = json.dumps({"draws": draws}, ensure_ascii=False, separators=(",", ":"))
    pending = path.with_suffix(".tmp")
    pending.write_text(content + "\n", encoding="utf-8", newline="\n")
    pending.replace(path)


def main() -> None:
    payload = export_payload()
    path = PROJECT_ROOT / "docs" / "data" / "lotto649.json"
    history_path = path.with_name("649-history.json")
    history = export_history(payload["draws"], history_path)
    write_history(history_path, history)
    print(f"Exported {len(history)} historical Lotto draws")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {payload['draw_count']} Lotto draws; latest {payload['latest_draw_date']}")


if __name__ == "__main__":
    main()
