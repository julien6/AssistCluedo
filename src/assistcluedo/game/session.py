from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from assistcluedo.framework.models import Scenario
from assistcluedo.framework.serialization import read_json, write_json


@dataclass
class PlayerNote:
    created_at: str
    text: str


@dataclass
class GameSession:
    id: str
    scenario_id: str
    player_id: str | None
    state: str
    started_at: str
    completed_at: str | None
    opened_document_ids: list[str] = field(default_factory=list)
    notes: list[PlayerNote] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    answer_evidence: dict[str, list[str]] = field(default_factory=dict)
    answer_confidence: dict[str, int] = field(default_factory=dict)
    score: int | None = None
    bookmarked_document_ids: list[str] = field(default_factory=list)

    @classmethod
    def new(cls, scenario: Scenario) -> GameSession:
        return cls(
            id=f"session_{scenario.seed:06d}",
            scenario_id=scenario.id,
            player_id=None,
            state="ready",
            started_at=datetime.now(UTC).isoformat(timespec="seconds"),
            completed_at=None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "player_id": self.player_id,
            "state": self.state,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "opened_document_ids": self.opened_document_ids,
            "notes": [note.__dict__ for note in self.notes],
            "answers": self.answers,
            "answer_evidence": self.answer_evidence,
            "answer_confidence": self.answer_confidence,
            "score": self.score,
            "bookmarked_document_ids": self.bookmarked_document_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GameSession:
        notes = [
            PlayerNote(created_at=str(note.get("created_at", "")), text=str(note.get("text", "")))
            for note in _dict_items(data.get("notes", []))
        ]
        player_value = data.get("player_id")
        completed_value = data.get("completed_at")
        score_value = data.get("score")
        return cls(
            id=str(data["id"]),
            scenario_id=str(data["scenario_id"]),
            player_id=None if player_value is None else str(player_value),
            state=str(data["state"]),
            started_at=str(data["started_at"]),
            completed_at=None if completed_value is None else str(completed_value),
            opened_document_ids=_string_list(data.get("opened_document_ids", [])),
            notes=notes,
            answers=_string_dict(data.get("answers", {})),
            answer_evidence={
                question_id: _string_list(document_ids)
                for question_id, document_ids in _object_dict(data.get("answer_evidence", {})).items()
            },
            answer_confidence=_int_dict(data.get("answer_confidence", {})),
            score=None if score_value is None else int(str(score_value)),
            bookmarked_document_ids=_string_list(data.get("bookmarked_document_ids", [])),
        )


def save_session(path: Path, session: GameSession) -> None:
    write_json(path, session.to_dict())


def load_session(path: Path) -> GameSession:
    return GameSession.from_dict(read_json(path))


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _int_dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(str(item)) for key, item in value.items()}
