from __future__ import annotations

import hashlib
import itertools
import json
from abc import ABC, abstractmethod
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
        desired_candidates = max(count * 12, 40)
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

        selected_candidates = _select_diverse(
            list(candidates.values()), count, overlap_limit, maximum - minimum + 1
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
        for candidate in primary:
            value = int(self.rng.choice(secondary_choices))
            candidate.pools[secondary_code] = [value]
            candidate.explanation["message"] += f" 第二區為{value:02d}。"
        _add_batch_metrics(primary, int(primary_pool["max"]) - int(primary_pool["min"]) + 1)
        return primary, diagnostics


class OrderedDigitGenerator(CandidateGenerator):
    def generate(  # type: ignore[override]
        self,
        count: int,
        *,
        pool: dict[str, Any],
        previous_numbers: list[int] | None = None,
        max_overlap: int | None = None,
        **_kwargs: Any,
    ) -> tuple[list[Candidate], dict[str, Any]]:
        digit_count = int(pool["pick_count"])
        candidates: list[Candidate] = []
        for digits_tuple in itertools.product(range(10), repeat=digit_count):
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
            candidates.append(
                Candidate(
                    pools={str(pool["code"]): digits},
                    structure=structure,
                    preference_score=round(
                        0.45 * repeat_preference + 0.45 * balance + 0.1 * seeded_tiebreaker,
                        6,
                    ),
                    explanation={
                        "temperature_counts": {},
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
            "attempts": 10**digit_count,
            "candidate_count": len(candidates),
            "requested_count": count,
            "generated_count": len(selected),
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


# 僅供內部使用；放在檔案末端避免讓演算法主流程被資料結構細節干擾。
from collections import Counter  # noqa: E402
