from __future__ import annotations

from dataclasses import dataclass

from assistcluedo.framework.models import (
    Character,
    Choice,
    GeneratedDocument,
    Location,
    QuizQuestion,
    Scenario,
)


@dataclass(frozen=True)
class PlayerCharacter:
    id: str
    name: str
    public_role: str
    capabilities: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "public_role": self.public_role,
            "capabilities": self.capabilities,
        }


@dataclass(frozen=True)
class PlayerLocation:
    id: str
    name: str
    location_type: str

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "location_type": self.location_type}


@dataclass(frozen=True)
class PlayerDocument:
    id: str
    title: str
    text: str
    visible_metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "visible_metadata": self.visible_metadata,
        }


@dataclass(frozen=True)
class PlayerQuizQuestion:
    id: str
    category: str
    text: str
    choices: list[Choice]
    difficulty: float

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "category": self.category,
            "text": self.text,
            "choices": [choice.to_dict() for choice in self.choices],
            "difficulty": self.difficulty,
        }


@dataclass(frozen=True)
class PlayerPackage:
    introduction: dict[str, object]
    characters: list[PlayerCharacter]
    locations: list[PlayerLocation]
    documents: list[PlayerDocument]
    quiz: list[PlayerQuizQuestion]


def build_player_package(scenario: Scenario) -> PlayerPackage:
    return PlayerPackage(
        introduction=player_introduction_for(scenario),
        characters=[player_character_for(character) for character in scenario.world.characters],
        locations=[player_location_for(location) for location in scenario.world.locations],
        documents=[player_document_for(document) for document in scenario.documents],
        quiz=[player_question_for(question) for question in scenario.questions],
    )


def player_introduction_for(scenario: Scenario) -> dict[str, object]:
    victim = next(char for char in scenario.world.characters if char.id == scenario.ground_truth.victim_id)
    return {
        "title": "Death at Blackwood Manor",
        "context": (
            f"{victim.name} was found dead during a private Sunday gathering at Blackwood Manor. "
            "The house was closed to outsiders, and the available evidence has been compiled for review."
        ),
        "objective": "Read the case documents, take notes, answer the quiz, and identify the hidden scenario.",
        "seed": scenario.seed,
    }


def player_document_for(document: GeneratedDocument) -> PlayerDocument:
    return PlayerDocument(
        id=document.id,
        title=document.title,
        text=document.text,
        visible_metadata={str(key): value for key, value in document.visible_metadata.items()},
    )


def player_question_for(question: QuizQuestion) -> PlayerQuizQuestion:
    return PlayerQuizQuestion(
        id=question.id,
        category=question.category,
        text=question.text,
        choices=question.choices,
        difficulty=question.difficulty,
    )


def player_character_for(character: Character) -> PlayerCharacter:
    return PlayerCharacter(
        id=character.id,
        name=character.name,
        public_role=character.public_role,
        capabilities=character.capabilities,
    )


def player_location_for(location: Location) -> PlayerLocation:
    return PlayerLocation(id=location.id, name=location.name, location_type=location.location_type)
