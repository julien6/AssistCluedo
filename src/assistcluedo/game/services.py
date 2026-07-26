from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from assistcluedo.framework.export import introduction_for
from assistcluedo.framework.models import GeneratedDocument, QuizQuestion, Scenario
from assistcluedo.game.evaluation import evaluate_scenario
from assistcluedo.game.session import GameSession, PlayerNote, load_session, save_session


class CasePresentationService:
    def introduction(self, scenario: Scenario) -> dict[str, object]:
        return introduction_for(scenario)

    def public_character_lines(self, scenario: Scenario) -> list[str]:
        return [f"- {character.name}: {character.public_role}" for character in scenario.world.characters]

    def public_location_lines(self, scenario: Scenario) -> list[str]:
        return [f"- {location.name} ({location.location_type})" for location in scenario.world.locations]


class SaveGameManager:
    def save(self, path: Path, session: GameSession) -> None:
        save_session(path, session)

    def load(self, path: Path) -> GameSession:
        return load_session(path)


class DocumentBrowser:
    def by_type(self, documents: list[GeneratedDocument], document_type: str) -> list[GeneratedDocument]:
        return [document for document in documents if document.visible_metadata.get("type") == document_type]

    def bookmarked(self, documents: list[GeneratedDocument], session: GameSession) -> list[GeneratedDocument]:
        bookmarked_ids = set(session.bookmarked_document_ids)
        return [document for document in documents if document.id in bookmarked_ids]

    def search(self, documents: list[GeneratedDocument], query: str) -> list[GeneratedDocument]:
        normalized = query.lower()
        return [
            document
            for document in documents
            if normalized in document.title.lower() or normalized in document.text.lower()
        ]

    def document_types(self, documents: list[GeneratedDocument]) -> list[tuple[str, int]]:
        types = sorted({str(document.visible_metadata["type"]) for document in documents})
        return [
            (document_type, sum(1 for document in documents if document.visible_metadata["type"] == document_type))
            for document_type in types
        ]

    def mark_opened(self, session: GameSession, document_id: str) -> None:
        if document_id not in session.opened_document_ids:
            session.opened_document_ids.append(document_id)
        session.state = "investigating"

    def toggle_bookmark(self, session: GameSession, document_id: str) -> bool:
        if document_id in session.bookmarked_document_ids:
            session.bookmarked_document_ids.remove(document_id)
            return False
        session.bookmarked_document_ids.append(document_id)
        return True


class PlayerNotebook:
    def add_note(self, session: GameSession, text: str) -> PlayerNote | None:
        normalized = text.strip()
        if not normalized:
            return None
        note = PlayerNote(datetime.now(UTC).isoformat(timespec="seconds"), normalized)
        session.notes.append(note)
        return note


class QuizController:
    def choice_map(self, question: QuizQuestion) -> dict[str, str]:
        return {
            chr(ord("a") + index): choice.id
            for index, choice in enumerate(question.choices)
        }

    def record_answer(
        self,
        session: GameSession,
        question_id: str,
        choice_id: str,
        confidence: int | None = None,
    ) -> None:
        session.answers[question_id] = choice_id
        session.answer_evidence[question_id] = list(session.opened_document_ids)
        if confidence is not None:
            session.answer_confidence[question_id] = confidence

    def submit(self, scenario: Scenario, session: GameSession) -> dict[str, object]:
        report = evaluate_scenario(scenario, session.answers, session.answer_evidence, session.answer_confidence)
        score = report["score"]
        if isinstance(score, dict):
            session.score = int(score["total"])
        session.state = "solution_revealed"
        session.completed_at = datetime.now(UTC).isoformat(timespec="seconds")
        return report


class SolutionPresenter:
    def solution_lines(self, scenario: Scenario) -> list[str]:
        truth = scenario.ground_truth
        name = {character.id: character.name for character in scenario.world.characters}
        location = {item.id: item.name for item in scenario.world.locations}
        obj = {item.id: item.name for item in scenario.world.objects}
        lines = [
            "Solution",
            (
                f"{name[truth.culprit_id]} killed {name[truth.victim_id]} at "
                f"{truth.incident_time:%H:%M} in {location[truth.location_id]} using the "
                f"{obj[truth.weapon_id]}."
            ),
            f"Motive: {truth.motive}.",
            f"False lead: {name[truth.false_lead_character_id]}.",
            f"Exculpated suspect: {name[truth.exculpated_character_id]}.",
            "Authoritative timeline",
        ]
        for event in scenario.events:
            actors = ", ".join(name.get(actor, actor) for actor in event.actor_ids)
            place = location.get(event.location_id, "off record") if event.location_id is not None else "off record"
            lines.append(f"- {event.start_time:%H:%M}: {event.event_type} | {actors} | {place}")
        return lines
