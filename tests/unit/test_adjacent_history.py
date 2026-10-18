import json
import sqlite3

import pytest

from scripts import backtest_539_adjacent as replay


@pytest.mark.parametrize("partial_database", [False, True])
def test_official_snapshot_retained_with_partial_or_missing_database(
    tmp_path, monkeypatch, partial_database
):
    draws = [
        {"draw_no": f"9600000{i}", "draw_date": f"2007-01-0{i}", "numbers": [1, 2, 3, 4, 5]}
        for i in range(1, 4)
    ]
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/539-adjacent-source.json").write_text(json.dumps(draws))
    (tmp_path / "docs/data").mkdir(parents=True)
    (tmp_path / "docs/data/daily539.json").write_text(
        json.dumps({"draws": [dict(draws[-1], source_status="official")]})
    )
    if partial_database:
        (tmp_path / "data/database").mkdir(parents=True)
        with sqlite3.connect(tmp_path / "data/database/numeris.sqlite3") as db:
            db.executescript("""
                CREATE TABLE games (id INTEGER, game_code TEXT);
                CREATE TABLE draws (id INTEGER, draw_no TEXT, draw_date TEXT,
                    verification_status TEXT, source_status TEXT, game_id INTEGER);
                CREATE TABLE draw_numbers (draw_id INTEGER, pool_code TEXT,
                    number_value INTEGER, is_special INTEGER);
                INSERT INTO games VALUES (1, 'TW_DAILY539');
                INSERT INTO draws VALUES (1, '96000003', '2007-01-03', 'verified', 'official', 1);
                INSERT INTO draws VALUES
                    (2, 'F0001', '2007-01-01', 'fixture_verified', 'fixture', 1);
            """)
            db.executemany(
                "INSERT INTO draw_numbers VALUES (1, 'main', ?, 0)", [(n,) for n in range(1, 6)]
            )
            db.executemany(
                "INSERT INTO draw_numbers VALUES (2, 'main', ?, 0)", [(n,) for n in range(6, 11)]
            )
    monkeypatch.setattr(replay, "ROOT", tmp_path)
    loaded, audit = replay.load()
    assert loaded == draws
    assert audit["history_snapshot_draws"] == 3
    assert audit["database_official_draws"] == int(partial_database)
