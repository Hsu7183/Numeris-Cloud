from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.services.generation.generators import (
    BingoGenerator,
    MultiPoolGenerator,
    OrderedDigitGenerator,
    UnorderedCombinationGenerator,
    recommended_coverage_target,
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


def test_fast_coverage_strategy_branches() -> None:
    assert recommended_coverage_target("ordered_digits", 3) == 3
    assert recommended_coverage_target("high_frequency", 4) == 3
    assert recommended_coverage_target("unordered_unique_numbers", 6) == 3
    assert recommended_coverage_target("unordered_unique_numbers", 5) == 2
    assert recommended_coverage_target("unordered_unique_numbers", 4) == 4

    coverage, diagnostics = UnorderedCombinationGenerator(17).generate(
        3,
        pool=_pool(),
        metrics=_metrics(),
        temperature_constraint=False,
        use_temperature_preference=False,
        selection_strategy="coverage",
        coverage_target_hits=2,
        allowed_odd_counts=list(range(5)),
        allowed_high_counts=list(range(5)),
        max_overlap=1,
        max_attempts=3000,
    )
    assert len(coverage) == 3
    assert diagnostics["coverage_target_hits"] == 2
    assert diagnostics["covered_target_subsets"] > 0
    assert diagnostics["target_subset_efficiency"] > 0

    with pytest.raises(GenerationError, match="覆蓋門檻"):
        UnorderedCombinationGenerator(17).generate(
            1,
            pool=_pool(),
            metrics=_metrics(),
            selection_strategy="coverage",
            coverage_target_hits=5,
            max_attempts=1000,
        )

    secondary = {
        "code": "second",
        "min": 1,
        "max": 3,
        "draw_count": 1,
        "pick_count": 1,
    }
    multi, multi_diagnostics = MultiPoolGenerator(21).generate(
        3,
        pools=[_pool("first"), secondary],
        metrics_by_pool={"first": _metrics(), "second": _metrics()[:3]},
        previous_by_pool={"first": [1, 4, 7, 10], "second": [1]},
        selection_strategy="coverage",
        coverage_target_hits=2,
        temperature_constraint=False,
        allowed_odd_counts=list(range(5)),
        allowed_high_counts=list(range(5)),
        max_attempts=3000,
        max_overlap=1,
    )
    assert len(multi) == 3
    assert multi_diagnostics["secondary_pool_strategy"] == "round_robin_coverage"
    assert multi_diagnostics["secondary_pool_coverage"] == 3

    ordered, ordered_diagnostics = OrderedDigitGenerator(23).generate(
        4,
        pool={"code": "digits", "pick_count": 2},
        selection_strategy="coverage",
        coverage_target_hits=2,
        max_overlap=1,
    )
    assert len(ordered) == 4
    assert ordered_diagnostics["attempts"] == 100
    assert (
        ordered_diagnostics["selection_strategy"]
        == "maximum_distinct_position_coverage"
    )
