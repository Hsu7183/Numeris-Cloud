from __future__ import annotations

import os
from pathlib import Path

TEST_DATABASE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "cache"
    / f"numeris_pytest_{os.getpid()}.sqlite3"
)
TEST_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
os.environ["NUMERIS_DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"


def pytest_sessionstart() -> None:
    from app.core.database import Base, SessionLocal, engine
    from app.models import database_models  # noqa: F401
    from app.services.bootstrap import initialize_catalog
    from app.services.importers.draw_importer import bulk_import_rows, generate_fixture_rows

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        initialize_catalog(db)
        rows = generate_fixture_rows(60)
        bulk_import_rows(
            db,
            rows,
            source_name="pytest固定官方樣本",
            source_locator="tests/generated",
            local_path=str(TEST_DATABASE_PATH),
            official=True,
        )


def pytest_sessionfinish() -> None:
    from app.core.database import engine

    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        TEST_DATABASE_PATH.with_name(TEST_DATABASE_PATH.name + suffix).unlink(
            missing_ok=True
        )
