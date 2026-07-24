from __future__ import annotations

import pytest

from app.services.analytics.core import (
    analyze_numbers,
    analyze_ordered_positions,
    calculate_ac,
    calculate_structure,
    jaccard_similarity,
    ordered_digit_structure,
)


def test_ac_consecutive_numbers_is_zero() -> None:
    assert calculate_ac([1, 2, 3, 4, 5, 6]) == 0


def test_ac_hand_calculated_case() -> None:
    # 差值集合：{1,2,3,4,5,6,8,9,11}，9種；k-1為4。
    assert calculate_ac([1, 2, 4, 7, 12]) == 4


@pytest.mark.parametrize("numbers", ([1, 1, 2], [1, 2]))
def test_ac_rejects_invalid_input(numbers: list[int]) -> None:
    with pytest.raises(ValueError):
        calculate_ac(numbers)


def test_frequency_omission_and_classification() -> None:
    draws = [[1, 2], [2, 3], [1, 4], [2, 4]]
    metrics = analyze_numbers(draws, 1, 5, 2, ["1", "2", "3", "4"])
    by_number = {item["number"]: item for item in metrics}
    assert by_number[2]["frequency"] == 3
    assert by_number[2]["current_omission"] == 0
    assert by_number[1]["current_omission"] == 1
    assert by_number[3]["current_omission"] == 2
    assert by_number[5]["current_omission"] == 4
    assert by_number[2]["temperature"] == "熱"
    assert by_number[5]["temperature"] == "冷"
    assert by_number[1]["last_seen_draw_no"] == "3"


def test_frequency_lookback_changes_result() -> None:
    full = analyze_numbers([[1], [1], [2]], 1, 3, 1)
    recent = analyze_numbers([[2]], 1, 3, 1)
    assert next(item for item in full if item["number"] == 1)["frequency"] == 2
    assert next(item for item in recent if item["number"] == 1)["frequency"] == 0


def test_frequency_input_validation() -> None:
    assert analyze_numbers([], 1, 3, 1) == []
    with pytest.raises(ValueError, match="範圍"):
        analyze_numbers([[1]], 3, 1, 1)
    with pytest.raises(ValueError, match="個數"):
        analyze_numbers([[1, 2]], 1, 3, 1)
    with pytest.raises(ValueError, match="範圍"):
        analyze_numbers([[4]], 1, 3, 1)
    with pytest.raises(ValueError, match="期別"):
        analyze_numbers([[1]], 1, 3, 1, [])


def test_ordered_positions_are_analyzed_independently() -> None:
    positions = analyze_ordered_positions(
        [[1, 9, 1], [1, 8, 2], [1, 7, 3], [2, 6, 4]],
        0,
        9,
        3,
        ["1", "2", "3", "4"],
    )
    first_position = {item["number"]: item for item in positions[0]}
    second_position = {item["number"]: item for item in positions[1]}
    assert first_position[1]["frequency"] == 3
    assert second_position[1]["frequency"] == 0
    assert first_position[1]["temperature"] == "熱"
    assert len(positions) == 3


def test_structure_metrics() -> None:
    structure = calculate_structure(
        [1, 2, 4, 7, 12],
        high_boundary=7,
        zones=[[1, 5], [6, 10], [11, 15]],
        previous_numbers=[2, 6, 11],
    )
    assert structure["sum"] == 26
    assert structure["span"] == 11
    assert structure["odd_count"] == 2
    assert structure["high_count"] == 2
    assert structure["zone_counts"] == [3, 1, 1]
    assert structure["consecutive_pairs"] == 1
    assert structure["last_draw_overlap"] == 1
    assert structure["last_draw_adjacent"] >= 2
    assert structure["prime_count"] == 2
    assert structure["ac"] == 4


def test_structure_without_ac_and_empty_rejected() -> None:
    assert calculate_structure([1], 2, [[1, 3]], include_ac=False)["ac"] is None
    with pytest.raises(ValueError):
        calculate_structure([], 2, [[1, 3]])


@pytest.mark.parametrize(
    ("digits", "pattern"),
    [
        ([1, 2, 3], "ABC"),
        ([1, 1, 2], "AAB"),
        ([1, 1, 1], "AAA"),
        ([0, 1, 2, 3], "ABCD"),
        ([0, 0, 1, 2], "AABC"),
        ([0, 0, 1, 1], "AABB"),
        ([0, 0, 0, 1], "AAAB"),
        ([0, 0, 0, 0], "AAAA"),
    ],
)
def test_ordered_digit_patterns(digits: list[int], pattern: str) -> None:
    structure = ordered_digit_structure(digits, digits)
    assert structure["repeat_pattern"] == pattern
    assert structure["same_position_count"] == len(digits)
    assert structure["ac"] is None


def test_ordered_digit_range_and_jaccard() -> None:
    with pytest.raises(ValueError):
        ordered_digit_structure([0, 10, 2])
    assert jaccard_similarity([1, 2], [2, 3]) == pytest.approx(1 / 3)
    assert jaccard_similarity([], []) == 1.0
