from __future__ import annotations

from pathlib import Path
from typing import Any

from assistcluedo.framework.export import load_exported_scenario
from assistcluedo.framework.serialization import read_json, write_json
from assistcluedo.game.evaluation import evaluate_scenario
from assistcluedo.game.session import load_session


def review_export(export_dir: Path) -> str:
    scenario = load_exported_scenario(export_dir)
    results_path = export_dir / "evaluation" / "results.json"
    if results_path.exists():
        report = read_json(results_path)
    else:
        session_path = export_dir / "session.json"
        if not session_path.exists():
            raise ValueError(f"No results.json or session.json found in {export_dir}.")
        session = load_session(session_path)
        if not session.answers:
            raise ValueError(f"No submitted answers found in {session_path}.")
        report = evaluate_scenario(scenario, session.answers, session.answer_evidence, session.answer_confidence)
        write_json(results_path, report)
    return render_review(report)


def render_review(report: dict[str, Any]) -> str:
    score = report["score"]
    solution = report["solution"]
    lines = [
        f"Scenario: {report['scenario_id']} | seed={report['seed']} | difficulty={report['difficulty']}",
        f"Score: {score['total']}/100 ({score['correct']}/{score['possible']})",
        "Categories:",
    ]
    for category, accuracy in sorted(score["accuracy_by_category"].items()):
        weighted = score["weighted_by_category"].get(category, 0)
        lines.append(f"- {category}: {accuracy}/100 accuracy, {weighted} weighted point(s)")
    lines.append("")
    lines.append("Answer review:")
    for question in report["questions"]:
        status = "correct" if question["is_correct"] else "wrong"
        evidence = ", ".join(question["supporting_document_ids"]) or "none"
        facts = ", ".join(question.get("supporting_fact_ids", [])) or "none"
        events = ", ".join(question.get("supporting_event_ids", [])) or "none"
        opened = ", ".join(question.get("opened_document_ids_before_answer", [])) or "none"
        confidence = question.get("confidence")
        confidence_text = f"{confidence}/5" if confidence is not None else "not recorded"
        lines.extend(
            [
                f"- {question['id']} [{question['category']}] {status}",
                f"  Q: {question['text']}",
                f"  Your answer: {question['player_choice_text']}",
                f"  Correct answer: {question['correct_choice_text']}",
                f"  Supporting evidence: {evidence}",
                f"  Supporting facts: {facts}",
                f"  Supporting events: {events}",
                f"  Documents opened before answer: {opened}",
                f"  Confidence: {confidence_text}",
                "  Choice review:",
            ]
        )
        for choice in question.get("choice_reviews", []):
            marker = "correct" if choice["is_correct"] else "incorrect"
            lines.append(f"    - {choice['choice_text']} [{marker}]: {choice['review']}")
    lines.append("")
    lines.append(
        "Solution: "
        f"culprit={solution['culprit_id']}, victim={solution['victim_id']}, "
        f"location={solution['location_id']}, weapon={solution['weapon_id']}, "
        f"time={solution['incident_time']}"
    )
    return "\n".join(lines)
