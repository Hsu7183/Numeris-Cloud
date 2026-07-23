from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.services.analytics.core import analyze_numbers, jaccard_similarity
from app.services.generation.generators import (
    BingoGenerator,
    MultiPoolGenerator,
    OrderedDigitGenerator,
    UnorderedCombinationGenerator,
)


@pytest.fixture
def pool49() -> dict[str, object]:
    return {
        "code": "main",
        "min": 1,
        "max": 49,
        "draw_count": 6,
        "pick_count": 6,
        "unique": True,
        "ordered": False,
        "high_boundary": 25,
        "zones": [[1, 10], [11, 20], [21, 30], [31, 40], [41, 49]],
    }


@pytest.fixture
def metrics49() -> list[dict[str, object]]:
    draws = [[((index * 7 + offset * 8) % 49) + 1 for offset in range(6)] for index in range(30)]
    draws = [sorted(set(draw)) for draw in draws]
    # 公式在少數期可能碰撞；以固定補值維持6個不重複號碼。
    fixed = []
    for draw in draws:
        candidate = list(draw)
        value = 1
        while len(candidate) < 6:
            if value not in candidate:
                candidate.append(value)
            value += 1
        fixed.append(sorted(candidate))
    return analyze_numbers(fixed, 1, 49, 6)


def test_unordered_generator_constraints_and_reproducibility(
    pool49: dict[str, object], metrics49: list[dict[str, object]]
) -> None:
    kwargs = {
        "count": 10,
        "pool": pool49,
        "metrics": metrics49,
        "previous_numbers": [1, 8, 15, 22, 29, 36],
        "allowed_odd_counts": [2, 3, 4],
        "allowed_high_counts": [2, 3, 4],
        "max_overlap": 3,
        "max_attempts": 50000,
    }
    first, first_diag = UnorderedCombinationGenerator(12345).generate(**kwargs)
    second, _ = UnorderedCombinationGenerator(12345).generate(**kwargs)
    assert [item.pools for item in first] == [item.pools for item in second]
    assert first_diag["constraints_relaxed"] is False
    assert len({item.ticket_hash for item in first}) == 10
    for item in first:
        numbers = item.primary_numbers
        assert len(numbers) == 6
        assert len(set(numbers)) == 6
        assert all(1 <= number <= 49 for number in numbers)
        assert item.structure["odd_count"] in [2, 3, 4]
        assert item.structure["high_count"] in [2, 3, 4]
    for index, left in enumerate(first):
        for right in first[index + 1 :]:
            assert len(set(left.primary_numbers) & set(right.primary_numbers)) <= 3
            assert 0 <= jaccard_similarity(left.primary_numbers, right.primary_numbers) <= 1


def test_different_seed_can_change_result(
    pool49: dict[str, object], metrics49: list[dict[str, object]]
) -> None:
    kwargs = {"count": 4, "pool": pool49, "metrics": metrics49, "max_attempts": 20000}
    first, _ = UnorderedCombinationGenerator(1).generate(**kwargs)
    second, _ = UnorderedCombinationGenerator(2).generate(**kwargs)
    assert [item.pools for item in first] != [item.pools for item in second]


def test_include_exclude_and_invalid_conditions(
    pool49: dict[str, object], metrics49: list[dict[str, object]]
) -> None:
    candidates, _ = UnorderedCombinationGenerator(10).generate(
        2,
        pool=pool49,
        metrics=metrics49,
        include_numbers=[1],
        exclude_numbers=[49],
        max_attempts=30000,
    )
    assert all(1 in item.primary_numbers and 49 not in item.primary_numbers for item in candidates)
    with pytest.raises(GenerationError, match="重疊"):
        UnorderedCombinationGenerator(1).generate(
            1, pool=pool49, metrics=metrics49, include_numbers=[1], exclude_numbers=[1]
        )
    with pytest.raises(GenerationError, match="超出"):
        UnorderedCombinationGenerator(1).generate(
            1, pool=pool49, metrics=metrics49, include_numbers=[99]
        )
    with pytest.raises(GenerationError, match="超過"):
        UnorderedCombinationGenerator(1).generate(
            1,
            pool=pool49,
            metrics=metrics49,
            include_numbers=list(range(1, 9)),
        )


def test_candidate_shortage_does_not_relax(
    pool49: dict[str, object], metrics49: list[dict[str, object]]
) -> None:
    with pytest.raises(GenerationError) as raised:
        UnorderedCombinationGenerator(1).generate(
            10,
            pool=pool49,
            metrics=metrics49,
            allowed_odd_counts=[6],
            allowed_high_counts=[6],
            ac_min=99,
            max_attempts=500,
        )
    assert raised.value.detail["constraints_relaxed"] is False


def test_multi_pool_generator(metrics49: list[dict[str, object]]) -> None:
    pools = [
        {
            "code": "first",
            "min": 1,
            "max": 38,
            "draw_count": 6,
            "pick_count": 6,
            "high_boundary": 20,
            "zones": [[1, 10], [11, 20], [21, 30], [31, 38]],
        },
        {"code": "second", "min": 1, "max": 8, "draw_count": 1, "pick_count": 1},
    ]
    metrics38 = [item for item in metrics49 if item["number"] <= 38]
    candidates, _ = MultiPoolGenerator(638).generate(
        5,
        pools=pools,
        metrics_by_pool={"first": metrics38, "second": metrics49[:8]},
        previous_by_pool={"first": [1, 2, 3, 4, 5, 6], "second": [1]},
        max_attempts=30000,
    )
    assert all(
        len(item.pools["first"]) == 6 and len(item.pools["second"]) == 1 for item in candidates
    )
    assert all(1 <= item.pools["second"][0] <= 8 for item in candidates)


def test_ordered_digit_generator_keeps_leading_zero() -> None:
    pool = {"code": "digits", "pick_count": 3}
    first, diag = OrderedDigitGenerator(305).generate(100, pool=pool, max_overlap=2)
    second, _ = OrderedDigitGenerator(305).generate(100, pool=pool, max_overlap=2)
    assert diag["candidate_count"] == 1000
    assert [item.pools for item in first] == [item.pools for item in second]
    assert any(item.primary_numbers[0] == 0 for item in first)
    assert all(len(item.primary_numbers) == 3 for item in first)
    assert all(item.structure["ac"] is None for item in first)


def test_bingo_generator() -> None:
    pool = {
        "code": "main",
        "min": 1,
        "max": 80,
        "draw_count": 20,
        "pick_count": 5,
        "high_boundary": 41,
        "zones": [[1, 20], [21, 40], [41, 60], [61, 80]],
    }
    draws = [list(range(start, start + 20)) for start in range(1, 21)]
    metrics = analyze_numbers(draws, 1, 80, 20)
    candidates, _ = BingoGenerator(80).generate(
        5, pool=pool, metrics=metrics, max_overlap=2, max_attempts=30000
    )
    assert all(len(item.primary_numbers) == 5 for item in candidates)
    assert all(len(set(item.primary_numbers)) == 5 for item in candidates)
