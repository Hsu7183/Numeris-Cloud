from __future__ import annotations

import io
import zipfile

from app.services.data_sources.official import (
    _parse_hkjc_draws,
    _parse_taiwan_annual_zip,
)


def test_taiwan_annual_zip_identifies_game_from_csv_content() -> None:
    csv_text = (
        "遊戲名稱,期別,開獎日期,獎號1,獎號2,獎號3,獎號4,獎號5,獎號6,特別號\n"
        "大樂透,115000001,2026-01-02,1,2,3,4,5,6,7\n"
    )
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("ªº¼Ö³z.csv", csv_text.encode("utf-8-sig"))

    rows, skipped = _parse_taiwan_annual_zip(archive_buffer.getvalue())

    assert skipped == []
    assert rows == [
        {
            "market_code": "TW",
            "game_code": "TW_LOTTO649",
            "draw_no": "115000001",
            "draw_date": "2026-01-02",
            "pool_code": "main",
            "numbers": [1, 2, 3, 4, 5, 6],
            "draw_order_known": False,
            "source_reference": "台灣彩券官方年度開獎結果檔",
            "special_number": 7,
        }
    ]


def test_hkjc_parser_keeps_only_completed_six_plus_special_results() -> None:
    rows = _parse_hkjc_draws(
        {
            "data": {
                "lotteryDraws": [
                    {
                        "year": 2026,
                        "no": 79,
                        "drawDate": "2026-07-23+08:00",
                        "status": "Result",
                        "drawResult": {
                            "drawnNo": ["4", "7", "15", "29", "32", "46"],
                            "xDrawnNo": "23",
                        },
                    },
                    {
                        "year": 2026,
                        "no": 80,
                        "drawDate": "2026-07-25+08:00",
                        "status": "Pending",
                        "drawResult": {"drawnNo": [], "xDrawnNo": None},
                    },
                ]
            }
        }
    )

    assert rows == [
        {
            "market_code": "HK",
            "game_code": "HK_MARKSIX",
            "draw_no": "26/079",
            "draw_date": "2026-07-23",
            "pool_code": "main",
            "numbers": [4, 7, 15, 29, 32, 46],
            "special_number": 23,
            "source_reference": "香港賽馬會六合彩官方GraphQL",
        }
    ]
