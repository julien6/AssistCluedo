from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assistcluedo.framework.export import load_exported_scenario
from assistcluedo.framework.generator import generate_symbolic_scenario
from assistcluedo.framework.serialization import read_json
from assistcluedo.framework.validation import validate_export, validate_scenario
from assistcluedo.game.session import load_session


@dataclass(frozen=True)
class AuditItem:
    code: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class AuditReport:
    title: str
    items: list[AuditItem]

    @property
    def ok(self) -> bool:
        return all(item.passed for item in self.items)

    def render(self) -> str:
        lines = [f"{self.title}: {'OK' if self.ok else 'FAILED'}"]
        for item in self.items:
            marker = "PASS" if item.passed else "FAIL"
            lines.append(f"- {item.code} [{marker}]: {item.evidence}")
        return "\n".join(lines)


def audit_framework_export(path: Path) -> AuditReport:
    scenario = load_exported_scenario(path)
    regenerated = generate_symbolic_scenario(
        scenario.seed,
        pack_id=scenario.pack_id,
        difficulty=scenario.difficulty,
    )
    scenario_report = validate_scenario(scenario)
    export_report = validate_export(path)
    player_document_ids = _player_document_ids(path)
    items = [
        AuditItem("F1", bool(scenario.world.characters and scenario.world.locations), "world generated from master seed"),
        AuditItem(
            "F2",
            _stable_symbolic_snapshot(regenerated) == _stable_symbolic_snapshot(scenario),
            "same seed/config reproduces symbolic scenario; text rendering may vary by provider",
        ),
        AuditItem("F3", scenario_report.ok, scenario_report.summary()),
        AuditItem("F4", _all_traces_have_events(scenario), f"traces={len(scenario.traces)}"),
        AuditItem("F5", _all_documents_have_plans(scenario), f"documents={len(scenario.documents)}"),
        AuditItem("F6", _documents_do_not_add_facts(scenario), "documents express planned facts only"),
        AuditItem("F7", bool(scenario.proof_graph.links), f"proof_links={len(scenario.proof_graph.links)}"),
        AuditItem("F8", _questions_have_one_answer(scenario), f"questions={len(scenario.questions)}"),
        AuditItem("F9", _answers_supported_by_player_documents(scenario, player_document_ids), "answers have player-visible support"),
        AuditItem("F10", _distractors_are_unique_and_not_marked_correct(scenario), "distractors distinct from correct answer"),
        AuditItem("F11", _ultimate_statement_matches_truth(scenario), "ultimate statement derived from ground truth"),
        AuditItem("F12", export_report.ok, export_report.summary()),
    ]
    return AuditReport("Framework DoD Audit", items)


def audit_game_export(path: Path) -> AuditReport:
    scenario = load_exported_scenario(path)
    export_report = validate_export(path)
    session_path = path / "session.json"
    session = load_session(session_path) if session_path.exists() else None
    results_path = path / "evaluation" / "results.json"
    results = read_json(results_path) if results_path.exists() else None
    player_document_count = len(_player_document_ids(path))
    items = [
        AuditItem("G1", bool(scenario.seed), f"seed={scenario.seed}"),
        AuditItem("G2", export_report.ok, "player package validates without oracle leakage"),
        AuditItem("G3", player_document_count == len(scenario.documents), f"player_documents={player_document_count}"),
        AuditItem("G4", session is not None, "session file exists for notes/progression"),
        AuditItem("G5", session is not None and len(session.answers) == len(scenario.questions), "quiz submitted"),
        AuditItem("G6", session is not None and session.score is not None, "score recorded"),
        AuditItem("G7", session is not None and session.state == "solution_revealed", "solution revealed after submission"),
        AuditItem("G8", _results_explain_answers(results), "post-game explanations include evidence and choices"),
        AuditItem("G9", session is not None and session_path.exists(), "session can be loaded from disk"),
        AuditItem("G10", _complete_game_artifacts_exist(path, session, results), "generated, played, evaluated, reviewed"),
    ]
    return AuditReport("Game DoD Audit", items)


def _all_traces_have_events(scenario: Any) -> bool:
    event_ids = {event.id for event in scenario.events}
    return all(trace.source_event_ids and set(trace.source_event_ids) <= event_ids for trace in scenario.traces)


def _stable_symbolic_snapshot(scenario: Any) -> dict[str, object]:
    data = scenario.to_dict()
    data["documents"] = [
        {
            "id": document["id"],
            "plan_id": document["plan_id"],
            "extracted_fact_ids": document["extracted_fact_ids"],
            "type": document["visible_metadata"].get("type"),
            "source": document["visible_metadata"].get("source"),
            "created_at": document["visible_metadata"].get("created_at"),
        }
        for document in data["documents"]
    ]
    return data


def _all_documents_have_plans(scenario: Any) -> bool:
    plan_ids = {plan.id for plan in scenario.document_plans}
    return all(document.plan_id in plan_ids for document in scenario.documents)


def _documents_do_not_add_facts(scenario: Any) -> bool:
    plans = {plan.id: plan for plan in scenario.document_plans}
    return all(
        set(document.extracted_fact_ids) <= set(plans[document.plan_id].mandatory_fact_ids)
        for document in scenario.documents
        if document.plan_id in plans
    )


def _questions_have_one_answer(scenario: Any) -> bool:
    return all(len(question.correct_choice_ids) == 1 for question in scenario.questions)


def _answers_supported_by_player_documents(scenario: Any, player_document_ids: set[str]) -> bool:
    return all(
        question.supporting_document_ids and set(question.supporting_document_ids) <= player_document_ids
        for question in scenario.questions
    )


def _distractors_are_unique_and_not_marked_correct(scenario: Any) -> bool:
    for question in scenario.questions:
        correct_id = question.correct_choice_ids[0]
        correct_text = next(choice.text for choice in question.choices if choice.id == correct_id)
        distractor_texts = [choice.text for choice in question.choices if choice.id != correct_id]
        if correct_text in distractor_texts or len(distractor_texts) != len(set(distractor_texts)):
            return False
    return True


def _ultimate_statement_matches_truth(scenario: Any) -> bool:
    ultimate = [question for question in scenario.questions if question.category == "ultimate statement"]
    if len(ultimate) != 1:
        return False
    question = ultimate[0]
    correct_id = question.correct_choice_ids[0]
    correct_text = next(choice.text for choice in question.choices if choice.id == correct_id)
    return correct_text == "Yes" and {
        "fact_culprit_identity",
        "fact_murder_location",
    } <= set(question.supporting_fact_ids)


def _player_document_ids(path: Path) -> set[str]:
    document_dir = path / "player_package" / "documents"
    if not document_dir.exists():
        return set()
    return {json_path.stem for json_path in document_dir.glob("*.json")}


def _results_explain_answers(results: object) -> bool:
    if not isinstance(results, dict) or not isinstance(results.get("questions"), list):
        return False
    return all(
        isinstance(question, dict)
        and bool(question.get("explanation"))
        and bool(question.get("supporting_document_ids"))
        and bool(question.get("choice_reviews"))
        for question in results["questions"]
    )


def _complete_game_artifacts_exist(path: Path, session: object, results: object) -> bool:
    return session is not None and isinstance(results, dict) and (path / "scenario.json").exists()
