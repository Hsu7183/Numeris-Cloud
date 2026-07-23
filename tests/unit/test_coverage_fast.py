from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.services.generation.generators import (
    BingoGenerator,
    MultiPoolGenerator,
    OrderedDigitGenerator,
    UnorderedCombinationGenerator,
)


def _pool(code: str = "main") -> dict[str, object]:
    return {
        "code": code,
        "min": 1,
        "max": 12,
        "draw_count": 4,
        "pick_count": 4,
        "unique": True,
        "ordered": False,
        "high_boundary": 7,
        "zones": [[1, 4], [5, 8], [9, 12]],
    }


def _metrics() -> list[dict[str, object]]:
    labels = ["熱"] * 3 + ["溫"] * 6 + ["冷"] * 3
    return [
        {
            "number": number,
            "frequency": 13 - number,
            "percentile_rank": 1 - (number - 1) / 11,
            "current_omission": number % 5,
            "temperature": labels[number - 1],
        }
        for number in range(1, 13)
    ]


def test_fast_unordered_branches() -> None:
    generator = UnorderedCombinationGenerator(5)
    candidates, diagnostics = generator.generate(
        2,
        pool=_pool(),
        metrics=_metrics(),
        include_numbers=[1],
        exclude_numbers=[12],
        allowed_odd_counts=[2],
        allowed_high_counts=[1, 2, 3],
        max_overlap=2,
        max_attempts=2000,
    )
    assert len(candidates) == 2
    assert diagnostics["constraints_relaxed"] is False
    assert all(
        candidate.explanation["batch_metrics"]["duplicate_count"] == 0 for candidate in candidates
    )
    with pytest.raises(GenerationError):
        generator.generate(1, pool=_pool(), metrics=_metrics(), include_numbers=[99])
    with pytest.raises(GenerationError):
        generator.generate(
            1,
            pool=_pool(),
            metrics=_metrics(),
            exclude_numbers=list(range(1, 11)),
        )
    with pytest.raises(GenerationError) as shortage:
        generator.generate(
            3,
            pool=_pool(),
            metrics=_metrics(),
            allowed_odd_counts=[4],
            allowed_high_counts=[4],
            ac_min=99,
            max_attempts=30,
        )
    assert shortage.value.detail["constraints_relaxed"] is False


def test_fast_multi_ordered_and_bingo() -> None:
    primary = _pool("first")
    secondary = {
        "code": "second",
        "min": 1,
        "max": 3,
        "draw_count": 1,
        "pick_count": 1,
    }
    multi, _ = MultiPoolGenerator(9).generate(
        2,
        pools=[primary, secondary],
        metrics_by_pool={"first": _metrics(), "second": _metrics()[:3]},
        previous_by_pool={"first": [1, 4, 7, 10], "second": [1]},
        max_attempts=2000,
        max_overlap=2,
    )
    assert all("second" in candidate.pools for candidate in multi)

    ordered, diagnostics = OrderedDigitGenerator(2).generate(
        4, pool={"code": "digits", "pick_count": 2}, max_overlap=1
    )
    assert diagnostics["candidate_count"] == 100
    assert len(ordered) == 4

    bingo_pool = _pool()
    bingo_pool["pick_count"] = 3
    bingo, _ = BingoGenerator(3).generate(
        2,
        pool=bingo_pool,
        metrics=_metrics(),
        max_overlap=1,
        max_attempts=1000,
    )
    assert all(candidate.structure["ac"] is None for candidate in bingo)
