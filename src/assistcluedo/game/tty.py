from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from assistcluedo.framework.models import GeneratedDocument, Scenario
from assistcluedo.game.application import GameSessionManager
from assistcluedo.game.services import (
    CasePresentationService,
    DocumentBrowser,
    PlayerNotebook,
    QuizController,
    SaveGameManager,
    SolutionPresenter,
)
from assistcluedo.game.session import GameSession

CASE_PRESENTATION = CasePresentationService()
DOCUMENT_BROWSER = DocumentBrowser()
NOTEBOOK = PlayerNotebook()
QUIZ = QuizController()
SAVE_GAME = SaveGameManager()
SOLUTION = SolutionPresenter()


def start_game(
    seed: int,
    output_dir: Path | None = None,
    resume: bool = False,
    difficulty: str = "easy",
) -> None:
    loaded = GameSessionManager().start_new_or_resume(seed, output_dir, resume, difficulty)
    _play_loop(loaded.scenario, loaded.session, loaded.session_path)


def play_exported_game(export_dir: Path) -> None:
    loaded = GameSessionManager().play_export(export_dir)
    _play_loop(loaded.scenario, loaded.session, loaded.session_path)


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def _play_loop(scenario: Scenario, session: GameSession, session_path: Path) -> None:
    print("\nAssistCluedo - TTY")
    intro = CASE_PRESENTATION.introduction(scenario)
    print(f"\n{intro['title']}")
    print(str(intro["context"]))
    print(f"Objective: {intro['objective']}")
    print(f"Seed: {scenario.seed} | Difficulty: {scenario.difficulty}")
    while True:
        print("\nMenu")
        print("1. Characters")
        print("2. Locations")
        print("3. Documents")
        print("4. Search documents")
        print("5. Notes")
        print("6. Quiz and submit")
        print("7. Save")
        print("q. Quit")
        choice = _input("> ").lower()
        if choice == "1":
            _show_characters(scenario)
        elif choice == "2":
            _show_locations(scenario)
        elif choice == "3":
            _document_menu(scenario.documents, session, session_path)
        elif choice == "4":
            _search_documents(scenario.documents, session, session_path)
        elif choice == "5":
            _notes(session, session_path)
        elif choice == "6":
            _quiz(scenario, session, session_path)
            return
        elif choice == "7":
            SAVE_GAME.save(session_path, session)
            print(f"Saved to {session_path}")
        elif choice == "q":
            SAVE_GAME.save(session_path, session)
            print(f"Saved to {session_path}")
            return
        else:
            print("Unknown choice.")


def _show_characters(scenario: Scenario) -> None:
    print("\nCharacters")
    for line in CASE_PRESENTATION.public_character_lines(scenario):
        print(line)


def _show_locations(scenario: Scenario) -> None:
    print("\nLocations")
    for line in CASE_PRESENTATION.public_location_lines(scenario):
        print(line)


def _list_documents(documents: list[GeneratedDocument], session: GameSession) -> None:
    print("\nDocuments")
    for index, doc in enumerate(documents, start=1):
        marker = "opened" if doc.id in session.opened_document_ids else "new"
        bookmark = "*" if doc.id in session.bookmarked_document_ids else " "
        print(f"{index}. [{marker}] [{bookmark}] {doc.title} ({doc.visible_metadata['type']})")


def _document_menu(
    documents: list[GeneratedDocument],
    session: GameSession,
    session_path: Path,
) -> None:
    while True:
        print("\nDocument Browser")
        print("1. All documents")
        print("2. Filter by type")
        print("3. Bookmarks")
        print("b. Back")
        choice = _input("> ").lower()
        if choice == "1":
            _browse_documents(documents, session, session_path)
        elif choice == "2":
            _filter_documents(documents, session, session_path)
        elif choice == "3":
            bookmarked = DOCUMENT_BROWSER.bookmarked(documents, session)
            if bookmarked:
                _browse_documents(bookmarked, session, session_path)
            else:
                print("No bookmarked documents.")
        elif choice == "b":
            return


def _filter_documents(
    documents: list[GeneratedDocument],
    session: GameSession,
    session_path: Path,
) -> None:
    doc_types = DOCUMENT_BROWSER.document_types(documents)
    print("\nDocument types")
    for index, (doc_type, count) in enumerate(doc_types, start=1):
        print(f"{index}. {doc_type} ({count})")
    choice = _input("Choose type number, or b to go back: ").lower()
    if choice == "b":
        return
    if not choice.isdigit() or not 1 <= int(choice) <= len(doc_types):
        print("Enter a valid type number.")
        return
    doc_type = doc_types[int(choice) - 1][0]
    filtered = DOCUMENT_BROWSER.by_type(documents, doc_type)
    _browse_documents(filtered, session, session_path)


def _browse_documents(documents: list[GeneratedDocument], session: GameSession, session_path: Path) -> None:
    while True:
        _list_documents(documents, session)
        choice = _input("Open document number, or b to go back: ").lower()
        if choice == "b":
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(documents):
            print("Enter a valid document number.")
            continue
        doc = documents[int(choice) - 1]
        DOCUMENT_BROWSER.mark_opened(session, doc.id)
        SAVE_GAME.save(session_path, session)
        print(f"\n{doc.title}")
        print(
            f"Type: {doc.visible_metadata['type']} | "
            f"Reliability: {doc.visible_metadata['reliability']} | "
            f"Created: {doc.visible_metadata.get('created_at', 'unknown')}"
        )
        print(doc.text)
        if doc.id in session.bookmarked_document_ids:
            action = _input("\nPress Enter to continue, or u to remove bookmark: ").lower()
            if action == "u":
                DOCUMENT_BROWSER.toggle_bookmark(session, doc.id)
                SAVE_GAME.save(session_path, session)
        else:
            action = _input("\nPress Enter to continue, or m to bookmark: ").lower()
            if action == "m":
                DOCUMENT_BROWSER.toggle_bookmark(session, doc.id)
                SAVE_GAME.save(session_path, session)


def _search_documents(documents: list[GeneratedDocument], session: GameSession, session_path: Path) -> None:
    query = _input("Search query: ").lower()
    matches = DOCUMENT_BROWSER.search(documents, query)
    if not matches:
        print("No matching documents.")
        return
    _browse_documents(matches, session, session_path)


def _notes(session: GameSession, session_path: Path) -> None:
    while True:
        print("\nNotes")
        if session.notes:
            for index, note in enumerate(session.notes, start=1):
                print(f"{index}. {note.text} ({note.created_at})")
        else:
            print("No notes yet.")
        print("a. Add note")
        print("b. Back")
        choice = _input("> ").lower()
        if choice == "a":
            text = _input("Note text: ")
            if NOTEBOOK.add_note(session, text):
                SAVE_GAME.save(session_path, session)
        elif choice == "b":
            return


def _quiz(scenario: Scenario, session: GameSession, session_path: Path) -> None:
    session.state = "quiz_started"
    print("\nQuiz")
    for question in scenario.questions:
        print(f"\n{question.text}")
        letters = QUIZ.choice_map(question)
        for idx, choice in enumerate(question.choices):
            letter = chr(ord("A") + idx)
            print(f"{letter}. {choice.text}")
        while True:
            answer = _input("Answer: ").lower()
            if answer in letters:
                confidence = _confidence_prompt()
                QUIZ.record_answer(session, question.id, letters[answer], confidence)
                break
            print("Choose one listed option.")
    report = QUIZ.submit(scenario, session)
    SAVE_GAME.save(session_path, session)
    _show_results(scenario, report)


def _confidence_prompt() -> int | None:
    value = _input("Confidence 1-5, or Enter to skip: ")
    if not value:
        return None
    if value.isdigit() and 1 <= int(value) <= 5:
        return int(value)
    print("Confidence skipped.")
    return None


def _show_results(scenario: Scenario, report: dict[str, object]) -> None:
    score = cast(dict[str, Any], report["score"])
    question_results = cast(list[dict[str, Any]], report["questions"])
    print("\nResults")
    print(f"Score: {score['total']}/100 ({score['correct']}/{score['possible']})")
    for category, value in sorted(score["accuracy_by_category"].items()):
        weighted = score["weighted_by_category"].get(category, 0)
        print(f"- {category}: {value}/100 accuracy, {weighted} weighted point(s)")
    print("\nAnswer review")
    for result in question_results:
        status = "correct" if result["is_correct"] else "wrong"
        print(f"\n{result['text']}")
        print(f"Your answer: {result['player_choice_text']} ({status})")
        print(f"Correct answer: {result['correct_choice_text']}")
        print(f"Explanation: {result['explanation']}")
        print(f"Evidence: {', '.join(result['supporting_document_ids'])}")
        print(f"Timeline events: {', '.join(result.get('supporting_event_ids', [])) or 'none'}")
        print("Choice review:")
        for choice in result.get("choice_reviews", []):
            marker = "correct" if choice["is_correct"] else "incorrect"
            print(f"- {choice['choice_text']} [{marker}]: {choice['review']}")
        if result.get("confidence") is not None:
            print(f"Confidence: {result['confidence']}/5")
    _reveal_solution(scenario)


def _reveal_solution(scenario: Scenario) -> None:
    print()
    for line in SOLUTION.solution_lines(scenario):
        print(line)
