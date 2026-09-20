from __future__ import annotations

import json
from datetime import UTC, datetime

from app.api.draws import recent_daily539_draws
from app.core.database import Base, SessionLocal, engine
from app.core.paths import PROJECT_ROOT, ensure_directories
from app.services.bootstrap import initialize_catalog
from app.services.data_sources.official import create_update_job, run_update_job


OUTPUT_PATH = PROJECT_ROOT / "docs" / "data" / "daily539.json"


def prepare_database() -> None:
    ensure_directories()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        initialize_catalog(db)


def update_taiwan_draws() -> None:
    with SessionLocal() as db:
        job = create_update_job(db, "taiwan")
    run_update_job(str(job["job_uuid"]))


def export_payload() -> dict[str, object]:
    with SessionLocal() as db:
        payload = recent_daily539_draws(limit=200, db=db)
    payload["generated_at"] = datetime.now(UTC).isoformat()
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
