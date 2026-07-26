from __future__ import annotations

from pathlib import Path

from assistcluedo.framework.generator import generate_symbolic_scenario
from assistcluedo.game.evaluation import evaluate_scenario
from assistcluedo.game.services import (
    CasePresentationService,
    DocumentBrowser,
    PlayerNotebook,
    QuizController,
    SaveGameManager,
    SolutionPresenter,
)
from assistcluedo.game.session import GameSession, load_session, save_session


def test_document_browser_tracks_progress_and_bookmarks() -> None:
    scenario = generate_symbolic_scenario(42)
    session = GameSession.new(scenario)
    browser = DocumentBrowser()
    document = scenario.documents[0]

    assert browser.search(scenario.documents, document.title[:5])
    assert browser.by_type(scenario.documents, str(document.visible_metadata["type"]))
    browser.mark_opened(session, document.id)
    assert session.state == "investigating"
    assert session.opened_document_ids == [document.id]
    assert browser.toggle_bookmark(session, document.id)
    assert browser.bookmarked(scenario.documents, session) == [document]
    assert not browser.toggle_bookmark(session, document.id)
    assert session.bookmarked_document_ids == []


def test_case_presentation_service_exposes_public_case_text() -> None:
    scenario = generate_symbolic_scenario(42)
    service = CasePresentationService()
    intro = service.introduction(scenario)
    assert intro["title"] == "Death at Blackwood Manor"
    assert service.public_character_lines(scenario)[0].startswith("- ")
    assert service.public_location_lines(scenario)[0].startswith("- ")


def test_notebook_adds_trimmed_notes() -> None:
    scenario = generate_symbolic_scenario(42)
    session = GameSession.new(scenario)
    notebook = PlayerNotebook()

    assert notebook.add_note(session, "   ") is None
    note = notebook.add_note(session, "  suspect alibi weak  ")
    assert note is not None
    assert session.notes[0].text == "suspect alibi weak"


def test_quiz_controller_records_evidence_confidence_and_submits() -> None:
    scenario = generate_symbolic_scenario(42)
    session = GameSession.new(scenario)
    controller = QuizController()
    first_question = scenario.questions[0]
    first_document = scenario.documents[0]

    session.opened_document_ids.append(first_document.id)
    controller.record_answer(session, first_question.id, first_question.correct_choice_ids[0], confidence=4)
    assert session.answer_evidence[first_question.id] == [first_document.id]
    assert session.answer_confidence[first_question.id] == 4

    for question in scenario.questions[1:]:
        controller.record_answer(session, question.id, question.correct_choice_ids[0])
    report = controller.submit(scenario, session)
    assert session.score == 100
    assert session.state == "solution_revealed"
    assert report["questions"][0]["confidence"] == 4


def test_session_round_trip_preserves_answer_confidence(tmp_path: Path) -> None:
    scenario = generate_symbolic_scenario(42)
    session = GameSession.new(scenario)
    session.answer_confidence = {"q1": 5}
    path = tmp_path / "session.json"

    save_session(path, session)
    loaded = load_session(path)
    assert loaded.answer_confidence == {"q1": 5}


def test_save_game_manager_round_trip(tmp_path: Path) -> None:
    scenario = generate_symbolic_scenario(42)
    session = GameSession.new(scenario)
    session.opened_document_ids = ["doc_001"]
    path = tmp_path / "session.json"

    manager = SaveGameManager()
    manager.save(path, session)
    assert manager.load(path).opened_document_ids == ["doc_001"]


def test_evaluation_report_includes_confidence() -> None:
    scenario = generate_symbolic_scenario(42)
    answers = {question.id: question.correct_choice_ids[0] for question in scenario.questions}
    confidence = {scenario.questions[0].id: 3}
    report = evaluate_scenario(scenario, answers, answer_confidence=confidence)
    assert report["questions"][0]["confidence"] == 3
    assert report["questions"][1]["confidence"] is None


def test_solution_presenter_outputs_reveal_and_timeline() -> None:
    scenario = generate_symbolic_scenario(42)
    lines = SolutionPresenter().solution_lines(scenario)
    assert lines[0] == "Solution"
    assert any("Motive:" in line for line in lines)
    assert any("main_incident" in line for line in lines)
