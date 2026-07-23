from __future__ import annotations

import argparse
from collections import defaultdict

from app.core.database import SessionLocal
from app.core.paths import FIXTURE_DIR, ensure_directories
from app.services.bootstrap import initialize_catalog
from app.services.importers.draw_importer import (
    generate_fixture_rows,
    import_rows,
    summary_dict,
    write_fixture_csv,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 Numeris 遊戲、規則、preset與fixture")
    parser.add_argument("--fixture", action="store_true", help="匯入固定測試資料")
    parser.add_argument("--draws", type=int, default=60, help="每個彩種fixture期數")
    args = parser.parse_args()
    ensure_directories()
    with SessionLocal() as db:
        catalog = initialize_catalog(db)
        print(f"已初始化 {catalog['games']} 種遊戲與 {catalog['presets']} 個preset。")
        if args.fixture:
            rows = generate_fixture_rows(args.draws)
            fixture_path = FIXTURE_DIR / "numeris_fixture.csv"
            write_fixture_csv(rows, fixture_path)
            by_game: dict[str, list[dict[str, object]]] = defaultdict(list)
            for row in rows:
                by_game[str(row["game_code"])].append(row)
            totals = {"processed": 0, "inserted": 0, "skipped": 0, "conflicts": 0, "errors": 0}
            for game_code, game_rows in by_game.items():
                summary = import_rows(
                    db,
                    game_rows,
                    source_name="Numeris固定測試fixture",
                    source_locator="tests/fixtures",
                    local_path=str(fixture_path),
                    official=False,
                )
                for key, value in summary_dict(summary).items():
                    totals[key] += value
                print(
                    f"{game_code}：新增 {summary.inserted}，略過 {summary.skipped}，"
                    f"衝突 {summary.conflicts}。"
                )
            print(f"fixture合計：{totals}")


if __name__ == "__main__":
    main()
