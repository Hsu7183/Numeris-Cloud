from __future__ import annotations

import hashlib
import itertools
import json
import math
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.exceptions import GenerationError
from app.services.analytics.core import (
    calculate_structure,
    jaccard_similarity,
    ordered_digit_structure,
)


@dataclass
class Candidate:
    pools: dict[str, list[int]]
    structure: dict[str, Any]
    preference_score: float
    diversity_score: float = 0.0
    explanation: dict[str, Any] = field(default_factory=dict)

    @property
    def ticket_hash(self) -> str:
        raw = json.dumps(self.pools, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @property
    def primary_numbers(self) -> list[int]:
        return next(iter(self.pools.values()))


class CandidateGenerator(ABC):
    def __init__(self, seed: int):
        self.seed = seed
        self.rng = np.random.Generator(np.random.PCG64(seed))

    @abstractmethod
    def generate(self, count: int, **kwargs: Any) -> tuple[list[Candidate], dict[str, Any]]:
        raise NotImplementedError


def _temperature_target(pick_count: int) -> dict[str, int]:
    if pick_count == 6:
        return {"熱": 2, "溫": 2, "冷": 2}
    if pick_count == 5:
        return {"熱": 2, "溫": 2, "冷": 1}
    hot = max(1, round(pick_count * 0.2))
    cold = max(1, round(pick_count * 0.2))
    if hot + cold > pick_count:
        cold = max(0, pick_count - hot)
    return {"熱": hot, "溫": pick_count - hot - cold, "冷": cold}


def _score_candidate(
    numbers: list[int],
    metrics_by_number: dict[int, dict[str, Any]],
    structure: dict[str, Any],
    ideal_odd: float,
    ideal_high: float,
    use_temperature_preference: bool = True,
) -> float:
    odd_balance = 1 - abs(float(structure["odd_count"]) - ideal_odd) / len(numbers)
    high_balance = 1 - abs(float(structure["high_count"]) - ideal_high) / len(numbers)
    if not use_temperature_preference:
        return round(max(0.0, min(1.0, odd_balance * 0.5 + high_balance * 0.5)), 6)
    frequency_score = sum(
        float(metrics_by_number[number]["percentile_rank"]) for number in numbers
    ) / len(numbers)
    omission_values = [
        float(metrics_by_number[number]["current_omission"]) for number in numbers
    ]
    omission_max = max(
        1.0,
        max(
            float(metric["current_omission"])
            for metric in metrics_by_number.values()
        ),
    )
    omission_score = sum(value / omission_max for value in omission_values) / len(
        numbers
    )
    return round(
        max(
            0.0,
            min(
                1.0,
                frequency_score * 0.35
                + omission_score * 0.25
                + odd_balance * 0.2
                + high_balance * 0.2,
            ),
        ),
        6,
    )


def _select_diverse(
    candidates: list[Candidate], count: int, max_overlap: int, pool_size: int
) -> list[Candidate]:
    if not candidates:
        return []
    remaining = sorted(candidates, key=lambda item: (-item.preference_score, item.ticket_hash))
    selected = [remaining.pop(0)]
    covered = set(selected[0].primary_numbers)
    while remaining and len(selected) < count:
        scored: list[tuple[float, str, Candidate]] = []
        for candidate in remaining:
            overlaps = [
                len(set(candidate.primary_numbers) & set(other.primary_numbers))
                for other in selected
            ]
            if max(overlaps) > max_overlap:
                continue
            distances = [
                1 - jaccard_similarity(candidate.primary_numbers, other.primary_numbers)
                for other in selected
            ]
            minimum_distance = min(distances)
            coverage = len(set(candidate.primary_numbers) - covered) / max(1, pool_size)
            adjusted = candidate.preference_score * 0.5 + minimum_distance * 0.3 + coverage * 0.2
            candidate.diversity_score = round(minimum_distance, 6)
            scored.append((adjusted, candidate.ticket_hash, candidate))
        if not scored:
            break
        best = max(scored, key=lambda item: (item[0], item[1]))[2]
        selected.append(best)
        remaining.remove(best)
        covered.update(best.primary_numbers)
    return selected


def recommended_coverage_target(game_type: str, pick_count: int) -> int:
    """Return the transparent analysis threshold used by coverage mode.

    The value is a comparison target, not a claim that every game awards a
    prize at that threshold. Ordered digit games require an exact positional
    match; unordered games use a low-tier coverage target.
    """
    if game_type == "ordered_digits":
        return pick_count
    if game_type == "high_frequency":
        return {
            1: 1,
            2: 2,
            3: 3,
            4: 3,
            5: 3,
            6: 4,
            7: 4,
            8: 4,
            9: 5,
            10: 5,
        }.get(pick_count, max(1, (pick_count + 1) // 2))
    if pick_count >= 6:
        return 3
    if pick_count >= 5:
        return 2
    return pick_count


def _coverage_keys(numbers: list[int], target_hits: int) -> set[tuple[int, ...]]:
    return {
        tuple(int(number) for number in subset)
        for subset in itertools.combinations(sorted(numbers), target_hits)
    }


def _select_max_coverage(
    candidates: list[Candidate],
    count: int,
    max_overlap: int,
    pool_size: int,
    target_hits: int,
) -> tuple[list[Candidate], dict[str, Any]]:
    """Greedily maximize distinct target-sized subsets across the ticket batch."""
    if not candidates:
        return [], {}
    remaining = sorted(
        candidates,
        key=lambda item: (-item.preference_score, item.ticket_hash),
    )
    selected: list[Candidate] = []
    covered_numbers: set[int] = set()
    covered_targets: set[tuple[int, ...]] = set()
    overlap_limit = max(0, max_overlap)
    relaxed_to = overlap_limit

    while remaining and len(selected) < count:
        scored: list[tuple[tuple[float, ...], Candidate, set[tuple[int, ...]]]] = []
        for candidate in remaining:
            numbers = set(candidate.primary_numbers)
            overlaps = [
                len(numbers & set(other.primary_numbers))
                for other in selected
            ]
            maximum_overlap = max(overlaps, default=0)
            if selected and maximum_overlap > relaxed_to:
                continue
            keys = _coverage_keys(candidate.primary_numbers, target_hits)
            marginal = len(keys - covered_targets)
            new_numbers = len(numbers - covered_numbers)
            minimum_distance = min(
                (
                    1
                    - jaccard_similarity(
                        candidate.primary_numbers,
                        other.primary_numbers,
                    )
                    for other in selected
                ),
                default=1.0,
            )
            score = (
                float(marginal),
                float(new_numbers),
                minimum_distance,
                -float(maximum_overlap),
                candidate.preference_score,
            )
            scored.append((score, candidate, keys))
        if not scored:
            relaxed_to += 1
            continue
        _, best, best_keys = max(
            scored,
            key=lambda item: (item[0], item[1].ticket_hash),
        )
        if selected:
            best.diversity_score = round(
                min(
                    1
                    - jaccard_similarity(
                        best.primary_numbers,
                        other.primary_numbers,
                    )
                    for other in selected
                ),
                6,
            )
        selected.append(best)
        remaining.remove(best)
        covered_numbers.update(best.primary_numbers)
        covered_targets.update(best_keys)

    theoretical_maximum = (
        len(selected) * math.comb(len(selected[0].primary_numbers), target_hits)
        if selected
        else 0
    )
    return selected, {
        "selection_strategy": "maximum_target_coverage",
        "coverage_target_hits": target_hits,
        "covered_target_subsets": len(covered_targets),
        "theoretical_target_subsets": theoretical_maximum,
        "target_subset_efficiency": (
            round(len(covered_targets) / theoretical_maximum, 6)
            if theoretical_maximum
            else 0.0
        ),
        "requested_max_overlap": overlap_limit,
        "effective_max_overlap": relaxed_to,
        "covered_numbers": len(covered_numbers),
        "pool_size": pool_size,
    }


class UnorderedCombinationGenerator(CandidateGenerator):
    def generate(  # type: ignore[override]
        self,
        count: int,
        *,
        pool: dict[str, Any],
        metrics: list[dict[str, Any]],
        previous_numbers: list[int] | None = None,
        include_numbers: list[int] | None = None,
        exclude_numbers: list[int] | None = None,
        allowed_odd_counts: list[int] | None = None,
        allowed_high_counts: list[int] | None = None,
        ac_min: int | None = None,
        ac_max: int | None = None,
        max_overlap: int | None = None,
        max_attempts: int = 50000,
        temperature_constraint: bool = True,
        use_temperature_preference: bool = True,
        include_ac: bool = True,
        selection_strategy: str = "preference",
        coverage_target_hits: int | None = None,
    ) -> tuple[list[Candidate], dict[str, Any]]:
        pick_count = int(pool["pick_count"])
        minimum, maximum = int(pool["min"]), int(pool["max"])
        include = sorted(set(include_numbers or []))
        exclude = set(exclude_numbers or [])
        if any(number < minimum or number > maximum for number in include + list(exclude)):
            raise GenerationError("GEN_INVALID_NUMBER", "包含或排除號碼超出合法範圍")
        if set(include) & exclude:
            raise GenerationError("GEN_CONFLICT", "包含與排除號碼不可重疊")
        if len(include) > pick_count:
            raise GenerationError("GEN_CONFLICT", "強制包含號碼超過每組選取數量")

        available = [number for number in range(minimum, maximum + 1) if number not in exclude]
        if len(available) < pick_count:
            raise GenerationError("GEN_CONFLICT", "排除條件使可用號碼不足")
        metrics_by_number = {int(item["number"]): item for item in metrics}
        categories = {
            label: [
                number for number in available if metrics_by_number[number]["temperature"] == label
            ]
            for label in ("熱", "溫", "冷")
        }
        target = _temperature_target(pick_count)
        allowed_odd = allowed_odd_counts or (
            [2, 3, 4]
            if pick_count == 6
            else [2, 3]
            if pick_count == 5
            else list(range(pick_count + 1))
        )
        allowed_high = allowed_high_counts or list(allowed_odd)
        overlap_limit = (
            max_overlap
            if max_overlap is not None
            else 3
            if pick_count == 6
            else 2
            if pick_count == 5
            else max(0, pick_count // 2)
        )

        candidates: dict[str, Candidate] = {}
        attempts = 0
        # 差異化選擇不需保存龐大候選池；較小批次可讓本機及coverage環境快速完成。
        desired_candidates = (
            max(count * 60, 300)
            if selection_strategy == "coverage"
            else max(count * 12, 40)
        )
        while attempts < max_attempts and len(candidates) < desired_candidates:
            attempts += 1
            selected = list(include)
            if temperature_constraint:
                selected_counts = Counter(
                    metrics_by_number[number]["temperature"] for number in selected
                )
                failed = False
                for label in ("熱", "溫", "冷"):
                    needed = max(0, target[label] - int(selected_counts.get(label, 0)))
                    choices = [number for number in categories[label] if number not in selected]
                    if len(choices) < needed:
                        failed = True
                        break
                    if needed:
                        sampled = self.rng.choice(choices, size=needed, replace=False).tolist()
                        selected.extend(int(number) for number in sampled)
                if failed or len(selected) > pick_count:
                    continue
            remaining_count = pick_count - len(selected)
            choices = [number for number in available if number not in selected]
            if len(choices) < remaining_count:
                continue
            if remaining_count:
                sampled = self.rng.choice(choices, size=remaining_count, replace=False).tolist()
                selected.extend(int(number) for number in sampled)
            numbers = sorted(selected)
            if len(numbers) != pick_count or len(set(numbers)) != pick_count:
                continue
            structure = calculate_structure(
                numbers,
                int(pool["high_boundary"]),
                pool["zones"],
                previous_numbers,
                include_ac=include_ac,
            )
            if int(structure["odd_count"]) not in allowed_odd:
                continue
            if int(structure["high_count"]) not in allowed_high:
                continue
            ac_value = structure["ac"]
            if ac_value is not None:
                ac = int(ac_value)
                if ac_min is not None and ac < ac_min:
                    continue
                if ac_max is not None and ac > ac_max:
                    continue
            if max(structure["zone_counts"]) == pick_count:
                continue
            score = _score_candidate(
                numbers,
                metrics_by_number,
                structure,
                pick_count / 2,
                pick_count / 2,
                use_temperature_preference,
            )
            category_counts = Counter(
                metrics_by_number[number]["temperature"] for number in numbers
            )
            candidate = Candidate(
                pools={str(pool["code"]): numbers},
                structure=structure,
                preference_score=score,
                explanation={
                    "temperature_counts": dict(category_counts),
                    "message": (
                        f"本組使用{category_counts.get('熱', 0)}個熱號、"
                        f"{category_counts.get('溫', 0)}個溫號及"
                        f"{category_counts.get('冷', 0)}個冷號；"
                        f"奇偶比為{structure['odd_count']}：{structure['even_count']}，"
                        f"大小比為{structure['high_count']}：{structure['low_count']}，"
                        f"和值為{structure['sum']}，AC值為{structure['ac']}。"
                    ),
                },
            )
            candidates[candidate.ticket_hash] = candidate

        coverage_diagnostics: dict[str, Any] = {}
        if selection_strategy == "coverage":
            target_hits = int(
                coverage_target_hits
                if coverage_target_hits is not None
                else recommended_coverage_target(
                    "high_frequency" if not include_ac else "unordered_unique_numbers",
                    pick_count,
                )
            )
            if target_hits < 1 or target_hits > pick_count:
                raise GenerationError(
                    "GEN_COVERAGE_TARGET",
                    "覆蓋門檻必須介於1與每組選號數之間",
                )
            selected_candidates, coverage_diagnostics = _select_max_coverage(
                list(candidates.values()),
                count,
                min(overlap_limit, max(0, target_hits - 1)),
                maximum - minimum + 1,
                target_hits,
            )
        else:
            selected_candidates = _select_diverse(
                list(candidates.values()),
                count,
                overlap_limit,
                maximum - minimum + 1,
            )
        diagnostics: dict[str, Any] = {
            "attempts": attempts,
            "candidate_count": len(candidates),
            "requested_count": count,
            "generated_count": len(selected_candidates),
            "max_overlap": overlap_limit,
            "temperature_constraint": temperature_constraint,
            "temperature_preference": use_temperature_preference,
            "constraints_relaxed": False,
            **coverage_diagnostics,
        }
        if len(selected_candidates) < count:
            diagnostics["suggestion"] = "可考慮增加最大重疊數、關閉AC限制或調整奇偶與大小條件"
            raise GenerationError(
                "GEN_CANDIDATE_SHORTAGE",
                "符合全部條件且具差異性的候選組合不足；系統未自動放寬條件",
                diagnostics,
            )
        _add_batch_metrics(selected_candidates, maximum - minimum + 1)
        return selected_candidates, diagnostics


class MultiPoolGenerator(CandidateGenerator):
    def generate(  # type: ignore[override]
        self,
        count: int,
        *,
        pools: list[dict[str, Any]],
        metrics_by_pool: dict[str, list[dict[str, Any]]],
        previous_by_pool: dict[str, list[int]] | None = None,
        **kwargs: Any,
    ) -> tuple[list[Candidate], dict[str, Any]]:
        coverage_mode = kwargs.get("selection_strategy") == "coverage"
        primary_pool = pools[0]
        base_generator = UnorderedCombinationGenerator(self.seed)
        primary, diagnostics = base_generator.generate(
            count,
            pool=primary_pool,
            metrics=metrics_by_pool[str(primary_pool["code"])],
            previous_numbers=(previous_by_pool or {}).get(str(primary_pool["code"])),
            **kwargs,
        )
        secondary_pool = pools[1]
        secondary_choices = list(range(int(secondary_pool["min"]), int(secondary_pool["max"]) + 1))
        secondary_code = str(secondary_pool["code"])
        secondary_offset = int(self.rng.integers(0, len(secondary_choices)))
        for index, candidate in enumerate(primary):
            value = (
                int(secondary_choices[(secondary_offset + index) % len(secondary_choices)])
                if coverage_mode
                else int(self.rng.choice(secondary_choices))
            )
            candidate.pools[secondary_code] = [value]
            candidate.explanation["message"] += f" 第二區為{value:02d}。"
        if coverage_mode:
            diagnostics["secondary_pool_strategy"] = "round_robin_coverage"
            diagnostics["secondary_pool_coverage"] = len(
                {candidate.pools[secondary_code][0] for candidate in primary}
            )
        _add_batch_metrics(primary, int(primary_pool["max"]) - int(primary_pool["min"]) + 1)
        return primary, diagnostics


class OrderedDigitGenerator(CandidateGenerator):
    def generate(  # type: ignore[override]
        self,
        count: int,
        *,
        pool: dict[str, Any],
        previous_numbers: list[int] | None = None,
        metrics_by_position: list[list[dict[str, Any]]] | None = None,
        use_temperature_preference: bool = True,
        max_overlap: int | None = None,
        selection_strategy: str = "preference",
        coverage_target_hits: int | None = None,
        **_kwargs: Any,
    ) -> tuple[list[Candidate], dict[str, Any]]:
        digit_count = int(pool["pick_count"])
        position_metrics = [
            {int(item["number"]): item for item in metrics}
            for metrics in (metrics_by_position or [])
        ]
        omission_maxima = [
            max(
                1.0,
                max(float(item["current_omission"]) for item in metrics.values()),
            )
            for metrics in position_metrics
        ]
        candidates: list[Candidate] = []
        total_combinations = 10**digit_count
        digit_tuples: Iterable[tuple[int, ...]]
        if selection_strategy == "coverage":
            candidate_budget = min(
                total_combinations,
                max(300, count * 60),
            )
            sampled_values = self.rng.choice(
                total_combinations,
                size=candidate_budget,
                replace=False,
            )
            digit_tuples = (
                tuple(int(char) for char in f"{int(value):0{digit_count}d}")
                for value in sampled_values
            )
        else:
            digit_tuples = itertools.product(range(10), repeat=digit_count)
        for digits_tuple in digit_tuples:
            digits = list(digits_tuple)
            structure = ordered_digit_structure(digits, previous_numbers)
            repeat_preference = (
                1.0 if structure["repeat_pattern"] in ("ABC", "ABCD", "AABC") else 0.7
            )
            balance = 1 - (
                abs(structure["odd_count"] - digit_count / 2)
                + abs(structure["high_count"] - digit_count / 2)
            ) / (2 * digit_count)
            seeded_tiebreaker = float(self.rng.random())
            position_temperatures: list[str] = []
            frequency_score = 0.5
            omission_score = 0.5
            if len(position_metrics) == digit_count:
                selected_metrics = [
                    position_metrics[position][digit]
                    for position, digit in enumerate(digits)
                ]
                position_temperatures = [
                    str(metric["temperature"]) for metric in selected_metrics
                ]
                frequency_score = sum(
                    float(metric["percentile_rank"])
                    for metric in selected_metrics
                ) / digit_count
                omission_score = sum(
                    float(metric["current_omission"])
                    / omission_maxima[position]
                    for position, metric in enumerate(selected_metrics)
                ) / digit_count
            if use_temperature_preference:
                preference_score = (
                    0.3 * repeat_preference
                    + 0.3 * balance
                    + 0.2 * frequency_score
                    + 0.15 * omission_score
                    + 0.05 * seeded_tiebreaker
                )
            else:
                preference_score = (
                    0.45 * repeat_preference
                    + 0.45 * balance
                    + 0.1 * seeded_tiebreaker
                )
            candidates.append(
                Candidate(
                    pools={str(pool["code"]): digits},
                    structure=structure,
                    preference_score=round(preference_score, 6),
                    explanation={
                        "temperature_counts": {},
                        "position_temperatures": position_temperatures,
                        "message": (
                            f"本組和值為{structure['sum']}，奇數位置{structure['odd_count']}個，"
                            f"大數字位置{structure['high_count']}個，"
                            f"重複型態為{structure['repeat_pattern']}；本遊戲不使用AC值。"
                        ),
                    },
                )
            )
        selected = _select_ordered_diverse(candidates, count, max_overlap or digit_count - 1)
        _add_batch_metrics(selected, 10 * digit_count)
        return selected, {
            "attempts": len(candidates),
            "candidate_count": len(candidates),
            "requested_count": count,
            "generated_count": len(selected),
            "position_temperature_analysis": len(position_metrics) == digit_count,
            "temperature_preference": use_temperature_preference,
            "selection_strategy": (
                "maximum_distinct_position_coverage"
                if selection_strategy == "coverage"
                else "preference"
            ),
            "coverage_target_hits": coverage_target_hits,
            "constraints_relaxed": False,
        }


class BingoGenerator(UnorderedCombinationGenerator):
    def generate(self, count: int, **kwargs: Any) -> tuple[list[Candidate], dict[str, Any]]:
        kwargs["temperature_constraint"] = False
        kwargs["include_ac"] = False
        kwargs["ac_min"] = None
        kwargs["ac_max"] = None
        return super().generate(count, **kwargs)


def _select_ordered_diverse(
    candidates: list[Candidate], count: int, max_same_positions: int
) -> list[Candidate]:
    remaining = sorted(candidates, key=lambda item: (-item.preference_score, item.ticket_hash))
    selected: list[Candidate] = []
    while remaining and len(selected) < count:
        if not selected:
            best = remaining.pop(0)
        else:
            eligible = [
                candidate
                for candidate in remaining
                if all(
                    sum(
                        a == b
                        for a, b in zip(
                            candidate.primary_numbers,
                            other.primary_numbers,
                            strict=False,
                        )
                    )
                    <= max_same_positions
                    for other in selected
                )
            ]
            if not eligible:
                break
            best = max(
                eligible,
                key=lambda candidate: (
                    min(
                        sum(
                            a != b
                            for a, b in zip(
                                candidate.primary_numbers,
                                other.primary_numbers,
                                strict=False,
                            )
                        )
                        for other in selected
                    ),
                    candidate.preference_score,
                    candidate.ticket_hash,
                ),
            )
            best.diversity_score = min(
                sum(
                    a != b
                    for a, b in zip(
                        best.primary_numbers,
                        other.primary_numbers,
                        strict=False,
                    )
                )
                / len(best.primary_numbers)
                for other in selected
            )
            remaining.remove(best)
        selected.append(best)
    return selected


def _add_batch_metrics(candidates: list[Candidate], pool_size: int) -> None:
    if not candidates:
        return
    overlaps = [
        len(set(left.primary_numbers) & set(right.primary_numbers))
        for left, right in itertools.combinations(candidates, 2)
    ]
    jaccards = [
        jaccard_similarity(left.primary_numbers, right.primary_numbers)
        for left, right in itertools.combinations(candidates, 2)
    ]
    coverage = set().union(*(set(candidate.primary_numbers) for candidate in candidates))
    batch = {
        "total_coverage": len(coverage),
        "coverage_rate": round(len(coverage) / pool_size, 6),
        "average_overlap": round(float(np.mean(overlaps)), 6) if overlaps else 0.0,
        "maximum_overlap": max(overlaps) if overlaps else 0,
        "average_jaccard": round(float(np.mean(jaccards)), 6) if jaccards else 0.0,
        "duplicate_count": len(candidates)
        - len({candidate.ticket_hash for candidate in candidates}),
    }
    for candidate in candidates:
        candidate.explanation["batch_metrics"] = batch
