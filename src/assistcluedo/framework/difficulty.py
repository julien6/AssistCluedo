from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DifficultyConfig:
    id: str
    characters: int
    locations: int
    contextual_events: int
    irrelevant_documents: int
    questions: int


DIFFICULTIES = {
    "easy": DifficultyConfig("easy", characters=6, locations=6, contextual_events=4, irrelevant_documents=2, questions=6),
    "medium": DifficultyConfig("medium", characters=8, locations=8, contextual_events=10, irrelevant_documents=5, questions=8),
    "hard": DifficultyConfig("hard", characters=10, locations=10, contextual_events=18, irrelevant_documents=8, questions=10),
    "spark": DifficultyConfig("spark", characters=10, locations=10, contextual_events=32, irrelevant_documents=14, questions=12),
}


def get_difficulty(name: str) -> DifficultyConfig:
    try:
        return DIFFICULTIES[name]
    except KeyError as exc:
        choices = ", ".join(sorted(DIFFICULTIES))
        raise ValueError(f"Unknown difficulty {name!r}. Available difficulties: {choices}.") from exc

