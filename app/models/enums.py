from __future__ import annotations

from enum import StrEnum


class GameType(StrEnum):
    UNORDERED = "unordered_unique_numbers"
    ORDERED = "ordered_digits"
    MULTI_POOL = "multi_pool"
    HIGH_FREQUENCY = "high_frequency"
    DERIVED = "derived_game"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
