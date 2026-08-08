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
    # locations: bumped so every difficulty seats all 10 required room themes (see world.py's
    # required-locations list) — "easy" used to cap out exactly at the old 6-item required list,
    # which structurally excluded garage/garden/servants_hall/conservatory no matter the seed.
    "easy": DifficultyConfig("easy", characters=6, locations=10, contextual_events=12, irrelevant_documents=6, questions=6),
    "medium": DifficultyConfig("medium", characters=8, locations=11, contextual_events=24, irrelevant_documents=12, questions=8),
    "hard": DifficultyConfig("hard", characters=10, locations=12, contextual_events=40, irrelevant_documents=20, questions=10),
    "spark": DifficultyConfig("spark", characters=10, locations=12, contextual_events=80, irrelevant_documents=40, questions=12),
}


def get_difficulty(name: str) -> DifficultyConfig:
    try:
        return DIFFICULTIES[name]
    except KeyError as exc:
        choices = ", ".join(sorted(DIFFICULTIES))
        raise ValueError(f"Unknown difficulty {name!r}. Available difficulties: {choices}.") from exc
