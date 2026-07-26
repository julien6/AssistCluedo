from __future__ import annotations

from pathlib import Path

from assistcluedo.framework.evaluation import Score, calculate_score
from assistcluedo.framework.models import QuizQuestion, Scenario
from assistcluedo.framework.serialization import read_json, write_json


def normalize_answers(raw_answers: object) -> dict[str, str]:
    if isinstance(raw_answers, dict):
        answers = raw_answers.get("answers", raw_answers)
        if isinstance(answers, dict):
            return {str(question_id): str(choice_id) for question_id, choice_id in answers.items()}
    raise ValueError("Answers JSON must be an object or an object with an 'answers' object.")


def load_answers(path: Path) -> dict[str, str]:
    return normalize_answers(read_json(path))


def evaluate_scenario(
    scenario: Scenario,
    answers: dict[str, str],
    answer_evidence: dict[str, list[str]] | None = None,
    answer_confidence: dict[str, int] | None = None,
) -> dict[str, object]:
    score = calculate_score(scenario.questions, answers)
    return evaluation_report_for(scenario, answers, score, answer_evidence, answer_confidence)


def evaluate_answers_file(
    scenario: Scenario,
    answers_path: Path,
    output_path: Path | None = None,
    answer_evidence: dict[str, list[str]] | None = None,
    answer_confidence: dict[str, int] | None = None,
) -> dict[str, object]:
    report = evaluate_scenario(scenario, load_answers(answers_path), answer_evidence, answer_confidence)
    if output_path is not None:
        write_json(output_path, report)
    return report


def answer_key_for(questions: list[QuizQuestion]) -> dict[str, list[str]]:
    return {question.id: question.correct_choice_ids for question in questions}


def evaluation_report_for(
    scenario: Scenario,
    answers: dict[str, str],
    score: Score,
    answer_evidence: dict[str, list[str]] | None = None,
    answer_confidence: dict[str, int] | None = None,
) -> dict[str, object]:
    answer_evidence = answer_evidence or {}
    answer_confidence = answer_confidence or {}
    return {
        "scenario_id": scenario.id,
        "seed": scenario.seed,
        "difficulty": scenario.difficulty,
        "score": {
            "total": score.total,
            "correct": score.correct,
            "possible": score.possible,
            "accuracy_by_category": score.by_category,
            "weighted_by_category": score.weighted_by_category,
        },
        "answers": answers,
        "answer_key": answer_key_for(scenario.questions),
        "questions": [
            _question_result_for(
                scenario,
                question,
                answers.get(question.id),
                answer_evidence.get(question.id, []),
                answer_confidence.get(question.id),
            )
            for question in scenario.questions
        ],
        "solution": _solution_for(scenario),
    }


def _question_result_for(
    scenario: Scenario,
    question: QuizQuestion,
    player_choice_id: str | None,
    opened_document_ids_before_answer: list[str],
    confidence: int | None,
) -> dict[str, object]:
    correct_choice_id = question.correct_choice_ids[0]
    correct_choice_text = _choice_text(question, correct_choice_id)
    return {
        "id": question.id,
        "category": question.category,
        "text": question.text,
        "player_choice_id": player_choice_id,
        "player_choice_text": _choice_text(question, player_choice_id),
        "correct_choice_id": correct_choice_id,
        "correct_choice_text": correct_choice_text,
        "is_correct": player_choice_id in question.correct_choice_ids,
        "explanation": question.explanation,
        "supporting_fact_ids": question.supporting_fact_ids,
        "supporting_document_ids": question.supporting_document_ids,
        "supporting_event_ids": _supporting_event_ids(scenario, question),
        "choice_reviews": _choice_reviews(question, correct_choice_id, correct_choice_text),
        "opened_document_ids_before_answer": opened_document_ids_before_answer,
        "confidence": confidence,
    }


def _choice_text(question: QuizQuestion, choice_id: str | None) -> str | None:
    for choice in question.choices:
        if choice.id == choice_id:
            return choice.text
    return None


def _supporting_event_ids(scenario: Scenario, question: QuizQuestion) -> list[str]:
    supporting_facts = set(question.supporting_fact_ids)
    supporting_documents = set(question.supporting_document_ids)
    document_facts = {
        fact_id
        for document in scenario.documents
        if document.id in supporting_documents
        for fact_id in document.extracted_fact_ids
    }
    candidate_facts = supporting_facts | document_facts
    event_ids = [
        event_id
        for trace in scenario.traces
        if candidate_facts & set(trace.fact_ids)
        for event_id in trace.source_event_ids
    ]
    return list(dict.fromkeys(event_ids))


def _choice_reviews(
    question: QuizQuestion,
    correct_choice_id: str,
    correct_choice_text: str | None,
) -> list[dict[str, object]]:
    reviews: list[dict[str, object]] = []
    for choice in question.choices:
        is_correct = choice.id == correct_choice_id
        if is_correct:
            review = "Correct: this choice matches the validated evidence path."
        else:
            review = (
                "Incorrect: this distractor is not supported by the validated evidence path; "
                f"the supported answer is {correct_choice_text}."
            )
        reviews.append(
            {
                "choice_id": choice.id,
                "choice_text": choice.text,
                "is_correct": is_correct,
                "review": review,
            }
        )
    return reviews


def _solution_for(scenario: Scenario) -> dict[str, object]:
    truth = scenario.ground_truth
    return {
        "culprit_id": truth.culprit_id,
        "victim_id": truth.victim_id,
        "location_id": truth.location_id,
        "weapon_id": truth.weapon_id,
        "motive": truth.motive,
        "incident_time": truth.incident_time.isoformat(),
        "false_lead_character_id": truth.false_lead_character_id,
        "exculpated_character_id": truth.exculpated_character_id,
    }
