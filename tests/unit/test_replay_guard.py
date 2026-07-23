from __future__ import annotations

import pytest

from app.services.replay.service import replay_input_draws


def test_replay_never_includes_target_or_future() -> None:
    draws = list(range(1, 31))
    inputs = replay_input_draws(draws, target_index=20, lookback=20)
    assert inputs == list(range(1, 21))
    assert 21 not in inputs
    assert all(value < 21 for value in inputs)


def test_replay_uses_available_history_only() -> None:
    assert replay_input_draws(list(range(10)), 4, 20) == [0, 1, 2, 3]
    with pytest.raises(ValueError):
        replay_input_draws(list(range(10)), 0, 5)
    with pytest.raises(ValueError):
        replay_input_draws(list(range(10)), 10, 5)
