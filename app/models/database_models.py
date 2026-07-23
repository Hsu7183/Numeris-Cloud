from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class SchemaMetadata(Base):
    __tablename__ = "schema_metadata"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    market_code: Mapped[str] = mapped_column(String(10), index=True)
    display_name_zh_tw: Mapped[str] = mapped_column(String(80))
    display_name_en: Mapped[str] = mapped_column(String(100))
    game_type: Mapped[str] = mapped_column(String(40))
    parent_game_code: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_ac: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_special_ball: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_multiple_pools: Mapped[bool] = mapped_column(Boolean, default=False)
    source_priority: Mapped[str] = mapped_column(String(80), default="official")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    rulesets: Mapped[list[Ruleset]] = relationship(back_populates="game")
    draws: Mapped[list[Draw]] = relationship(back_populates="game")


class Ruleset(Base):
    __tablename__ = "rulesets"
    __table_args__ = (UniqueConstraint("game_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    version: Mapped[str] = mapped_column(String(30))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source_reference: Mapped[str] = mapped_column(Text)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    game: Mapped[Game] = relationship(back_populates="rulesets")


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    market_code: Mapped[str] = mapped_column(String(10), index=True)
    source_name: Mapped[str] = mapped_column(String(100))
    source_locator: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(160))
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    etag: Mapped[str | None] = mapped_column(String(200))
    last_modified: Mapped[str | None] = mapped_column(String(200))
    parser_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    parse_status: Mapped[str] = mapped_column(String(30))
    validation_status: Mapped[str] = mapped_column(String(30))
    error_message: Mapped[str | None] = mapped_column(Text)


class Draw(Base):
    __tablename__ = "draws"
    __table_args__ = (
        UniqueConstraint("game_id", "draw_no"),
        Index("ix_draw_game_date", "game_id", "draw_date"),
        Index("ix_draw_verification", "verification_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"))
    draw_no: Mapped[str] = mapped_column(String(40))
    draw_date: Mapped[date] = mapped_column(Date)
    draw_datetime_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_timezone: Mapped[str] = mapped_column(String(40), default="Asia/Taipei")
    source_artifact_id: Mapped[int | None] = mapped_column(ForeignKey("source_artifacts.id"))
    source_status: Mapped[str] = mapped_column(String(30))
    verification_status: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    game: Mapped[Game] = relationship(back_populates="draws")
    numbers: Mapped[list[DrawNumber]] = relationship(
        back_populates="draw", cascade="all, delete-orphan", order_by="DrawNumber.id"
    )


class DrawNumber(Base):
    __tablename__ = "draw_numbers"
    id: Mapped[int] = mapped_column(primary_key=True)
    draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id", ondelete="CASCADE"), index=True)
    pool_code: Mapped[str] = mapped_column(String(40))
    draw_order: Mapped[int | None] = mapped_column(Integer)
    sorted_order: Mapped[int | None] = mapped_column(Integer)
    number_value: Mapped[int] = mapped_column(Integer)
    is_special: Mapped[bool] = mapped_column(Boolean, default=False)
    draw: Mapped[Draw] = relationship(back_populates="numbers")


class DrawFinancial(Base):
    __tablename__ = "draw_financials"
    id: Mapped[int] = mapped_column(primary_key=True)
    draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"), unique=True)
    currency: Mapped[str | None] = mapped_column(String(10))
    sales_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    sales_units: Mapped[int | None] = mapped_column(Integer)
    total_prize: Mapped[float | None] = mapped_column(Numeric(18, 2))
    jackpot_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    carryover_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    source_status: Mapped[str | None] = mapped_column(String(30))


class PrizeTier(Base):
    __tablename__ = "prize_tiers"
    id: Mapped[int] = mapped_column(primary_key=True)
    draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"), index=True)
    tier_code: Mapped[str] = mapped_column(String(40))
    tier_name: Mapped[str] = mapped_column(String(80))
    winning_condition_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    winning_units: Mapped[int | None] = mapped_column(Integer)
    prize_per_unit: Mapped[float | None] = mapped_column(Numeric(18, 2))
    total_tier_prize: Mapped[float | None] = mapped_column(Numeric(18, 2))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    cutoff_draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"))
    lookback_count: Mapped[int] = mapped_column(Integer)
    analysis_type: Mapped[str] = mapped_column(String(40))
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64))
    app_version: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    error_message: Mapped[str | None] = mapped_column(Text)


class NumberMetric(Base):
    __tablename__ = "number_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    pool_code: Mapped[str] = mapped_column(String(40))
    position_index: Mapped[int | None] = mapped_column(Integer)
    number_value: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[int] = mapped_column(Integer)
    frequency_rate: Mapped[float] = mapped_column(Float)
    expected_frequency: Mapped[float] = mapped_column(Float)
    frequency_zscore: Mapped[float] = mapped_column(Float)
    current_omission: Mapped[int] = mapped_column(Integer)
    average_gap: Mapped[float | None] = mapped_column(Float)
    maximum_gap: Mapped[int | None] = mapped_column(Integer)
    last_seen_draw_no: Mapped[str | None] = mapped_column(String(40))
    percentile_rank: Mapped[float] = mapped_column(Float)
    temperature_category: Mapped[str] = mapped_column(String(20))
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class GenerationPreset(Base):
    __tablename__ = "generation_presets"
    id: Mapped[int] = mapped_column(primary_key=True)
    preset_code: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(30))
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64))
    built_in: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    target_draw_no: Mapped[str] = mapped_column(String(40))
    target_draw_date: Mapped[date | None] = mapped_column(Date)
    cutoff_draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"))
    preset_id: Mapped[int] = mapped_column(ForeignKey("generation_presets.id"))
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id"))
    requested_ticket_count: Mapped[int] = mapped_column(Integer)
    generated_ticket_count: Mapped[int] = mapped_column(Integer)
    random_seed: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64))
    app_version: Mapped[str] = mapped_column(String(30))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    diagnostic_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    tickets: Mapped[list[GeneratedTicket]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="GeneratedTicket.ticket_index"
    )


class GeneratedTicket(Base):
    __tablename__ = "generated_tickets"
    __table_args__ = (UniqueConstraint("generation_run_id", "ticket_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_run_id: Mapped[int] = mapped_column(ForeignKey("generation_runs.id"))
    ticket_index: Mapped[int] = mapped_column(Integer)
    preference_score: Mapped[float] = mapped_column(Float)
    diversity_score: Mapped[float] = mapped_column(Float)
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    ticket_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[GenerationRun] = relationship(back_populates="tickets")
    numbers: Mapped[list[GeneratedTicketNumber]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="GeneratedTicketNumber.display_order",
    )


class GeneratedTicketNumber(Base):
    __tablename__ = "generated_ticket_numbers"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("generated_tickets.id"))
    pool_code: Mapped[str] = mapped_column(String(40))
    position_index: Mapped[int | None] = mapped_column(Integer)
    number_value: Mapped[int] = mapped_column(Integer)
    display_order: Mapped[int] = mapped_column(Integer)
    ticket: Mapped[GeneratedTicket] = relationship(back_populates="numbers")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_run_id: Mapped[int] = mapped_column(ForeignKey("generation_runs.id"), index=True)
    actual_draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"))
    status: Mapped[str] = mapped_column(String(30))
    error_message: Mapped[str | None] = mapped_column(Text)


class TicketResult(Base):
    __tablename__ = "ticket_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_run_id: Mapped[int] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("generated_tickets.id"))
    main_hit_count: Mapped[int] = mapped_column(Integer)
    special_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    pool_results_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    prize_tier_code: Mapped[str | None] = mapped_column(String(40))
    payout: Mapped[float | None] = mapped_column(Numeric(18, 2))
    payout_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReplayRun(Base):
    __tablename__ = "replay_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    preset_id: Mapped[int] = mapped_column(ForeignKey("generation_presets.id"))
    start_draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"))
    end_draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"))
    lookback_count: Mapped[int] = mapped_column(Integer)
    tickets_per_draw: Mapped[int] = mapped_column(Integer)
    seed_policy: Mapped[str] = mapped_column(String(40))
    baseline_repetitions: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    report_path: Mapped[str | None] = mapped_column(Text)


class ReplayDrawResult(Base):
    __tablename__ = "replay_draw_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    replay_run_id: Mapped[int] = mapped_column(ForeignKey("replay_runs.id"), index=True)
    target_draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"))
    cutoff_draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id"))
    generated_ticket_count: Mapped[int] = mapped_column(Integer)
    hit_distribution_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    baseline_distribution_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    job_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
