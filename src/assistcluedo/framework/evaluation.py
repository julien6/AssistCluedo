from __future__ import annotations

from dataclasses import dataclass

from assistcluedo.framework.models import QuizQuestion, Scenario


@dataclass(frozen=True)
class Score:
    total: int
    correct: int
    possible: int
    by_category: dict[str, int]
    weighted_by_category: dict[str, int]


CATEGORY_WEIGHTS = {
    "factual": 25,
    "temporal": 20,
    "causal": 20,
    "source assessment": 15,
    "hypothesis elimination": 10,
    "ultimate statement": 10,
}


def calculate_score(questions: list[QuizQuestion], answers: dict[str, str]) -> Score:
    possible = len(questions)
    correct = 0
    by_category: dict[str, int] = {}
    totals_by_category: dict[str, int] = {}
    for question in questions:
        totals_by_category[question.category] = totals_by_category.get(question.category, 0) + 1
        is_correct = answers.get(question.id) in question.correct_choice_ids
        if is_correct:
            correct += 1
            by_category[question.category] = by_category.get(question.category, 0) + 1
        else:
            by_category.setdefault(question.category, 0)
    category_accuracy = {
        category: round((by_category.get(category, 0) / total) * 100)
        for category, total in totals_by_category.items()
    }
    active_weight_total = sum(CATEGORY_WEIGHTS.get(category, 0) for category in totals_by_category)
    weighted_by_category: dict[str, int] = {}
    if active_weight_total:
        weighted_total = 0.0
        last_category = ""
        for category, question_count in totals_by_category.items():
            last_category = category
            raw_weight = CATEGORY_WEIGHTS.get(category, 0)
            normalized_weight = raw_weight / active_weight_total * 100
            category_points = (by_category.get(category, 0) / question_count) * normalized_weight
            weighted_by_category[category] = round(category_points)
            weighted_total += category_points
        total = round(weighted_total)
        rounded_delta = total - sum(weighted_by_category.values())
        if last_category and rounded_delta:
            weighted_by_category[last_category] += rounded_delta
    else:
        total = round((correct / possible) * 100) if possible else 0
        weighted_by_category = category_accuracy.copy()
    return Score(
        total=total,
        correct=correct,
        possible=possible,
        by_category=category_accuracy,
        weighted_by_category=weighted_by_category,
    )


def evaluate_answers(scenario: Scenario, answers: dict[str, str]) -> Score:
    return calculate_score(scenario.questions, answers)
