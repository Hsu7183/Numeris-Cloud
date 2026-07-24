from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from typing import Any


def calculate_ac(numbers: Sequence[int]) -> int:
    """計算無序、不重複組合的 AC 值。"""
    if len(numbers) < 3:
        raise ValueError("AC值至少需要3個號碼")
    if len(set(numbers)) != len(numbers):
        raise ValueError("AC值不接受重複號碼")
    ordered = sorted(numbers)
    differences = {
        ordered[j] - ordered[i] for i in range(len(ordered)) for j in range(i + 1, len(ordered))
    }
    return len(differences) - (len(ordered) - 1)


def classify_temperature(metrics: list[dict[str, Any]]) -> None:
    """使用可重現 tie-breaker 把號碼分為熱、溫、冷。"""
    ranked = sorted(
        metrics,
        key=lambda item: (
            -int(item["frequency"]),
            int(item["current_omission"]),
            -int(item["last_seen_index"]),
            int(item["number"]),
        ),
    )
    total = len(ranked)
    hot_count = max(1, math.ceil(total * 0.2))
    cold_count = max(1, math.ceil(total * 0.2))
    for index, item in enumerate(ranked):
        item["percentile_rank"] = 1.0 if total == 1 else 1 - index / (total - 1)
        if index < hot_count:
            item["temperature"] = "熱"
        elif index >= total - cold_count:
            item["temperature"] = "冷"
        else:
            item["temperature"] = "溫"


def analyze_numbers(
    draws: Sequence[Sequence[int]],
    minimum: int,
    maximum: int,
    draw_count: int,
    draw_nos: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if minimum > maximum:
        raise ValueError("號碼範圍錯誤")
    if not draws:
        return []
    draw_nos = draw_nos if draw_nos is not None else [str(index + 1) for index in range(len(draws))]
    if len(draw_nos) != len(draws):
        raise ValueError("期別數量與開獎資料不一致")
    for draw in draws:
        if len(draw) != draw_count:
            raise ValueError("開獎號碼個數與規則不符")
        if any(number < minimum or number > maximum for number in draw):
            raise ValueError("開獎號碼超出合法範圍")

    sample_count = len(draws)
    pool_size = maximum - minimum + 1
    probability = draw_count / pool_size
    expected = sample_count * probability
    stddev = math.sqrt(sample_count * probability * (1 - probability))
    metrics: list[dict[str, Any]] = []

    for number in range(minimum, maximum + 1):
        occurrence_indexes = [index for index, draw in enumerate(draws) if number in set(draw)]
        frequency = len(occurrence_indexes)
        last_index = occurrence_indexes[-1] if occurrence_indexes else -1
        omission = sample_count - 1 - last_index if last_index >= 0 else sample_count
        gaps = [
            occurrence_indexes[index] - occurrence_indexes[index - 1] - 1
            for index in range(1, len(occurrence_indexes))
        ]
        metrics.append(
            {
                "number": number,
                "frequency": frequency,
                "frequency_rate": frequency / sample_count,
                "expected_frequency": expected,
                "frequency_zscore": (frequency - expected) / stddev if stddev else 0.0,
                "current_omission": omission,
                "average_gap": statistics.fmean(gaps) if gaps else None,
                "maximum_gap": max(gaps) if gaps else None,
                "recent_gaps": gaps[-5:],
                "last_seen_draw_no": draw_nos[last_index] if last_index >= 0 else None,
                "last_seen_index": last_index,
            }
        )
    classify_temperature(metrics)
    return sorted(metrics, key=lambda item: int(item["number"]))


def analyze_ordered_positions(
    draws: Sequence[Sequence[int]],
    minimum: int,
    maximum: int,
    digit_count: int,
    draw_nos: Sequence[str] | None = None,
) -> list[list[dict[str, Any]]]:
    """依位置分開計算3星彩、4星彩的冷熱與遺漏。"""
    if any(len(draw) != digit_count for draw in draws):
        raise ValueError("開獎位數與規則不符")
    if any(
        digit < minimum or digit > maximum
        for draw in draws
        for digit in draw
    ):
        raise ValueError("開獎數字超出合法範圍")
    labels = (
        draw_nos
        if draw_nos is not None
        else [str(index + 1) for index in range(len(draws))]
    )
    return [
        analyze_numbers(
            [[int(draw[position])] for draw in draws],
            minimum,
            maximum,
            1,
            labels,
        )
        for position in range(digit_count)
    ]


def _consecutive_groups(numbers: Sequence[int]) -> tuple[int, int]:
    ordered = sorted(numbers)
    pairs = sum(1 for left, right in zip(ordered, ordered[1:], strict=False) if right - left == 1)
    groups = 0
    in_group = False
    for left, right in zip(ordered, ordered[1:], strict=False):
        if right - left == 1 and not in_group:
            groups += 1
            in_group = True
        elif right - left != 1:
            in_group = False
    return pairs, groups


def _is_prime(value: int) -> bool:
    if value < 2:
        return False
    return all(value % divisor for divisor in range(2, int(math.sqrt(value)) + 1))


def calculate_structure(
    numbers: Sequence[int],
    high_boundary: int,
    zones: Sequence[Sequence[int]],
    previous_numbers: Sequence[int] | None = None,
    include_ac: bool = True,
) -> dict[str, Any]:
    if not numbers:
        raise ValueError("號碼不可為空")
    ordered = sorted(numbers)
    gaps = [right - left for left, right in zip(ordered, ordered[1:], strict=False)]
    consecutive_pairs, consecutive_groups = _consecutive_groups(ordered)
    previous = set(previous_numbers or [])
    adjacent = {
        number
        for previous_number in previous
        for number in (previous_number - 1, previous_number + 1)
    }
    tails = Counter(number % 10 for number in ordered)
    zone_counts = [
        sum(1 for number in ordered if int(zone[0]) <= number <= int(zone[1])) for zone in zones
    ]
    result: dict[str, Any] = {
        "sum": sum(ordered),
        "span": max(ordered) - min(ordered),
        "odd_count": sum(number % 2 == 1 for number in ordered),
        "even_count": sum(number % 2 == 0 for number in ordered),
        "high_count": sum(number >= high_boundary for number in ordered),
        "low_count": sum(number < high_boundary for number in ordered),
        "zone_counts": zone_counts,
        "consecutive_pairs": consecutive_pairs,
        "consecutive_groups": consecutive_groups,
        "last_draw_overlap": len(set(ordered) & previous),
        "last_draw_adjacent": len(set(ordered) & adjacent),
        "same_tail_groups": sum(1 for count in tails.values() if count >= 2),
        "distinct_tail_count": len(tails),
        "prime_count": sum(_is_prime(number) for number in ordered),
        "minimum_gap": min(gaps) if gaps else 0,
        "maximum_gap": max(gaps) if gaps else 0,
        "average_gap": statistics.fmean(gaps) if gaps else 0.0,
        "standard_deviation": statistics.pstdev(ordered) if len(ordered) > 1 else 0.0,
    }
    result["ac"] = calculate_ac(ordered) if include_ac and len(ordered) >= 3 else None
    return result


def ordered_digit_structure(
    digits: Sequence[int], previous_digits: Sequence[int] | None = None
) -> dict[str, Any]:
    if any(digit < 0 or digit > 9 for digit in digits):
        raise ValueError("每一位數字必須介於0至9")
    counts = sorted(Counter(digits).values(), reverse=True)
    pattern_map = {
        (1, 1, 1): "ABC",
        (2, 1): "AAB",
        (3,): "AAA",
        (1, 1, 1, 1): "ABCD",
        (2, 1, 1): "AABC",
        (2, 2): "AABB",
        (3, 1): "AAAB",
        (4,): "AAAA",
    }
    previous = list(previous_digits or [])
    return {
        "sum": sum(digits),
        "odd_count": sum(digit % 2 == 1 for digit in digits),
        "high_count": sum(digit >= 5 for digit in digits),
        "span": max(digits) - min(digits),
        "repeat_pattern": pattern_map.get(tuple(counts), "其他"),
        "duplicate_digit_count": len(digits) - len(set(digits)),
        "adjacent_pairs": sum(
            abs(left - right) == 1
            for left, right in zip(digits, digits[1:], strict=False)
        ),
        "same_position_count": sum(
            digit == previous[index] for index, digit in enumerate(digits) if index < len(previous)
        ),
        "shared_digit_count": len(set(digits) & set(previous)),
        "ac": None,
    }


def jaccard_similarity(left: Sequence[int], right: Sequence[int]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 1.0
