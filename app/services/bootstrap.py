from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core.paths import CONFIG_DIR
from app.models.database_models import (
    Game,
    GenerationPreset,
    Ruleset,
    SchemaMetadata,
)


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_json_yaml(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def initialize_catalog(db: Session) -> dict[str, int]:
    game_count = 0
    preset_count = 0
    for path in sorted((CONFIG_DIR / "games").glob("*.yaml")):
        config = load_json_yaml(path)
        game = db.scalar(select(Game).where(Game.game_code == config["game_code"]))
        if game is None:
            game = Game(
                game_code=config["game_code"],
                market_code=config["market_code"],
                display_name_zh_tw=config["display_name_zh_tw"],
                display_name_en=config["display_name_en"],
                game_type=config["game_type"],
                parent_game_code=config.get("parent_game_code"),
                active=True,
                supports_ac=config["supports_ac"],
                supports_special_ball=config["supports_special_ball"],
                supports_multiple_pools=config["supports_multiple_pools"],
                source_priority="官方來源",
            )
            db.add(game)
            db.flush()
        ruleset = db.scalar(
            select(Ruleset).where(Ruleset.game_id == game.id, Ruleset.version == "1.0.0")
        )
        if ruleset is None:
            ruleset = Ruleset(
                game_id=game.id,
                version="1.0.0",
                status="active",
                verified=config["verified"],
                source_reference=config["source_reference"],
                config_json=config,
                config_hash=canonical_hash(config),
            )
            db.add(ruleset)
        game_count += 1

    for path in sorted((CONFIG_DIR / "presets").glob("*.yaml")):
        config = load_json_yaml(path)
        preset = db.scalar(
            select(GenerationPreset).where(GenerationPreset.preset_code == config["preset_code"])
        )
        if preset is None:
            db.add(
                GenerationPreset(
                    preset_code=config["preset_code"],
                    display_name=config["display_name"],
                    version=config["version"],
                    config_json=config,
                    config_hash=canonical_hash(config),
                    built_in=True,
                    active=True,
                )
            )
        preset_count += 1

    metadata = {
        "schema_version": "0001",
        "app_version": __version__,
        "last_migration": "0001_initial_schema",
    }
    for key, value in metadata.items():
        row = db.get(SchemaMetadata, key)
        if row is None:
            db.add(SchemaMetadata(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return {"games": game_count, "presets": preset_count}
