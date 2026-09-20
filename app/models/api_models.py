from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class GenerationRequest(BaseModel):
    game_code: str = "TW_LOTTO649"
    ticket_count: int = Field(default=10, ge=1, le=100)
    lookback_count: int = Field(default=20, ge=1, le=5000)
    random_seed: int = Field(default=20260723, ge=0)
    preset_code: str = "VIDEO_FIVE_STEP_V1"
    target_draw_no: str | None = None
    cutoff_draw_no: str | None = None
    max_overlap: int | None = Field(default=None, ge=0)
    star_count: int = Field(default=6, ge=1, le=10)
    include_numbers: list[int] = Field(default_factory=list)
    exclude_numbers: list[int] = Field(default_factory=list)
    allowed_odd_counts: list[int] | None = None
    allowed_high_counts: list[int] | None = None
    ac_min: int | None = None
    ac_max: int | None = None
    max_attempts: int = Field(default=50000, ge=100, le=500000)
    selection_strategy: Literal["preference", "coverage"] = "preference"
    coverage_target_hits: int | None = Field(default=None, ge=1, le=10)
    use_temperature_preference: bool = True

    @model_validator(mode="after")
    def check_number_lists(self) -> GenerationRequest:
        if set(self.include_numbers) & set(self.exclude_numbers):
            raise ValueError("強制包含與排除號碼不可重疊")
        return self


class ReplayRequest(BaseModel):
    game_code: str = "TW_LOTTO649"
    start_index: int = Field(default=20, ge=2)
    end_index: int | None = Field(default=None, ge=3)
    lookback_count: int = Field(default=20, ge=2)
    tickets_per_draw: int = Field(default=5, ge=1, le=50)
    random_seed: int = Field(default=20260723, ge=0)
    baseline_repetitions: int = Field(default=20, ge=1, le=500)
    strategy: Literal["video", "coverage"] = "video"
    cadence: Literal["draw", "week"] = "draw"
    star_count: int = Field(default=6, ge=1, le=10)


class SimpleGenerationRequest(BaseModel):
    game_code: str = "HK_MARKSIX"
    mode: Literal[
        "weekly",
        "coverage",
        "single",
        "wheel7",
        "wheel8",
        "wheel9",
    ] = "weekly"
    ticket_count: int = Field(default=10, ge=1, le=100)
    star_count: int = Field(default=6, ge=1, le=10)
    random_seed: int | None = Field(default=None, ge=0)
    refresh: bool = False


class ImportRow(BaseModel):
    market_code: str
    game_code: str
    draw_no: str
    draw_date: date
    pool_code: str = "main"
    numbers: list[int]
    special_number: int | None = None
    source_reference: str = "手動匯入"


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: dict[str, Any]
    request_id: str
