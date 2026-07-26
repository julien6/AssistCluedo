from __future__ import annotations

import json
import os
import random
import subprocess
from dataclasses import dataclass, replace
from typing import Protocol

from assistcluedo.framework.difficulty import DifficultyConfig
from assistcluedo.framework.models import (
    Location,
    QuizQuestion,
    Scenario,
    World,
    WorldObject,
)
from assistcluedo.framework.pack import Pack
from assistcluedo.framework.seed import rng_for


@dataclass(frozen=True)
class WorldContentResult:
    characters: dict[str, dict[str, str]]
    locations: dict[str, dict[str, str]]
    objects: dict[str, dict[str, str]]
    motives: list[str]
    provider: str
    attempts: int = 1
    fallback_used: bool = False


@dataclass(frozen=True)
class ScenarioTextResult:
    introduction: dict[str, str]
    questions: dict[str, dict[str, str]]
    provider: str
    attempts: int = 1
    fallback_used: bool = False


class ScenarioContentGenerator(Protocol):
    def generate_world_content(
        self,
        seed: int,
        pack: Pack,
        difficulty: DifficultyConfig,
        world: World,
    ) -> WorldContentResult:
        ...

    def generate_scenario_texts(self, scenario: Scenario) -> ScenarioTextResult:
        ...


class ProceduralContentGenerator:
    provider = "procedural"

    def generate_world_content(
        self,
        seed: int,
        pack: Pack,
        difficulty: DifficultyConfig,
        world: World,
    ) -> WorldContentResult:
        rng = rng_for(seed, "content")
        first_names = [
            "Ada",
            "Beatrice",
            "Celia",
            "Dorian",
            "Edmund",
            "Flora",
            "Gideon",
            "Helena",
            "Iris",
            "Jonas",
            "Lydia",
            "Marius",
            "Nora",
            "Oscar",
            "Sylvia",
            "Theo",
        ]
        surnames = [
            "Ashcombe",
            "Bellamy",
            "Cairn",
            "Davenport",
            "Ellis",
            "Fenwick",
            "Graves",
            "Hale",
            "Lark",
            "Merritt",
            "Pryce",
            "Vale",
            "Wexler",
            "Yardley",
        ]
        rng.shuffle(first_names)
        rng.shuffle(surnames)
        characters: dict[str, dict[str, str]] = {}
        for index, character in enumerate(world.characters):
            name = f"{first_names[index % len(first_names)]} {surnames[index % len(surnames)]}"
            if character.id == "general":
                name = f"General {surnames[index % len(surnames)]}"
            characters[character.id] = {
                "name": name,
                "public_role": _procedural_role(character.public_role, rng),
                "description": _procedural_character_description(character.public_role, rng),
            }

        locations = {
            location.id: {
                "name": _procedural_location_name(location, rng),
                "description": _procedural_location_description(location, rng),
            }
            for location in world.locations
        }
        objects = {
            obj.id: {
                "name": _procedural_object_name(obj, rng),
                "description": _procedural_object_description(obj, rng),
            }
            for obj in world.objects
        }
        motives = [_procedural_motive(motive, rng) for motive in pack.motives]
        return WorldContentResult(characters, locations, objects, motives, self.provider)

    def generate_scenario_texts(self, scenario: Scenario) -> ScenarioTextResult:
        victim = next(character for character in scenario.world.characters if character.id == scenario.ground_truth.victim_id)
        questions = {
            question.id: {
                "text": question.text,
                "explanation": question.explanation,
            }
            for question in scenario.questions
        }
        introduction = {
            "title": f"Case file: {victim.name}",
            "context": (
                f"{victim.name} died during a closed gathering at {scenario.world.attributes.get('setting_name', 'the manor')}. "
                "The witness material, private records, and system logs have been assembled for review."
            ),
            "objective": "Read the documents, keep notes, answer the quiz, and reconstruct what happened.",
        }
        return ScenarioTextResult(introduction, questions, self.provider)


class LocalLLMContentGenerator:
    provider = "local-llm"

    def __init__(self, command: str | None = None, model: str = "local") -> None:
        self.command = command or os.environ.get("ASSISTCLUEDO_LOCAL_LLM_COMMAND")
        self.model = model

    def generate_world_content(
        self,
        seed: int,
        pack: Pack,
        difficulty: DifficultyConfig,
        world: World,
    ) -> WorldContentResult:
        command = self._command()
        payload = _world_prompt(seed, pack, difficulty, world, self.model)
        completed = subprocess.run(command, input=payload, shell=True, check=True, capture_output=True, text=True)
        data = json.loads(completed.stdout)
        result = WorldContentResult(
            characters={str(key): _string_dict(value) for key, value in dict(data["characters"]).items()},
            locations={str(key): _string_dict(value) for key, value in dict(data["locations"]).items()},
            objects={str(key): _string_dict(value) for key, value in dict(data["objects"]).items()},
            motives=[str(item) for item in data["motives"]],
            provider=self.provider,
        )
        validate_world_content(world, result)
        return result

    def generate_scenario_texts(self, scenario: Scenario) -> ScenarioTextResult:
        command = self._command()
        completed = subprocess.run(
            command,
            input=_scenario_text_prompt(scenario, self.model),
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(completed.stdout)
        result = ScenarioTextResult(
            introduction=_string_dict(data["introduction"]),
            questions={str(key): _string_dict(value) for key, value in dict(data["questions"]).items()},
            provider=self.provider,
        )
        validate_scenario_texts(scenario, result)
        return result

    def _command(self) -> str:
        if self.command is None:
            raise RuntimeError("Set ASSISTCLUEDO_LOCAL_LLM_COMMAND to use local LLM content generation.")
        return self.command


class FallbackContentGenerator:
    def __init__(self, primary: ScenarioContentGenerator, fallback: ScenarioContentGenerator, max_attempts: int = 2) -> None:
        self.primary = primary
        self.fallback = fallback
        self.max_attempts = max_attempts

    def generate_world_content(
        self,
        seed: int,
        pack: Pack,
        difficulty: DifficultyConfig,
        world: World,
    ) -> WorldContentResult:
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.primary.generate_world_content(seed, pack, difficulty, world)
                validate_world_content(world, result)
                return replace(result, attempts=attempt, fallback_used=False)
            except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError):
                pass
        fallback = self.fallback.generate_world_content(seed, pack, difficulty, world)
        validate_world_content(world, fallback)
        return replace(fallback, attempts=self.max_attempts, fallback_used=True)

    def generate_scenario_texts(self, scenario: Scenario) -> ScenarioTextResult:
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.primary.generate_scenario_texts(scenario)
                validate_scenario_texts(scenario, result)
                return replace(result, attempts=attempt, fallback_used=False)
            except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError):
                pass
        fallback = self.fallback.generate_scenario_texts(scenario)
        validate_scenario_texts(scenario, fallback)
        return replace(fallback, attempts=self.max_attempts, fallback_used=True)


def content_generator_for(
    provider: str = "local-llm",
    fallback: str = "procedural",
    max_attempts: int = 2,
    model: str = "local",
) -> ScenarioContentGenerator:
    primary = _base_content_generator(provider, model)
    if provider == "procedural":
        return primary
    return FallbackContentGenerator(primary, _base_content_generator(fallback, model), max_attempts=max_attempts)


def apply_world_content(world: World, result: WorldContentResult, setting_name: str) -> World:
    characters = [
        replace(
            character,
            name=result.characters[character.id]["name"],
            public_role=result.characters[character.id]["public_role"],
            attributes={**character.attributes, "description": result.characters[character.id]["description"]},
        )
        for character in world.characters
    ]
    locations = [
        replace(
            location,
            name=result.locations[location.id]["name"],
            attributes={**location.attributes, "description": result.locations[location.id]["description"]},
        )
        for location in world.locations
    ]
    objects = [
        replace(
            obj,
            name=result.objects[obj.id]["name"],
            attributes={**obj.attributes, "description": result.objects[obj.id]["description"]},
        )
        for obj in world.objects
    ]
    return replace(
        world,
        characters=characters,
        locations=locations,
        objects=objects,
        attributes={
            **world.attributes,
            "setting_name": setting_name,
            "content_provider": result.provider,
            "content_fallback_used": result.fallback_used,
            "content_attempts": result.attempts,
        },
    )


def apply_scenario_texts(scenario: Scenario, result: ScenarioTextResult) -> Scenario:
    questions = [
        replace(
            question,
            text=result.questions.get(question.id, {}).get("text", question.text),
            explanation=result.questions.get(question.id, {}).get("explanation", question.explanation),
        )
        for question in scenario.questions
    ]
    return replace(
        scenario,
        questions=questions,
        public_introduction=dict(result.introduction),
        content_metadata={
            **scenario.content_metadata,
            "scenario_text_provider": result.provider,
            "scenario_text_fallback_used": result.fallback_used,
            "scenario_text_attempts": result.attempts,
        },
    )


def validate_world_content(world: World, result: WorldContentResult) -> None:
    _validate_entity_texts("character", [character.id for character in world.characters], result.characters)
    _validate_entity_texts("location", [location.id for location in world.locations], result.locations)
    _validate_entity_texts("object", [obj.id for obj in world.objects], result.objects)
    if len(result.motives) < 3 or any(not motive.strip() for motive in result.motives):
        raise ValueError("World content must include at least three non-empty motives.")


def validate_scenario_texts(scenario: Scenario, result: ScenarioTextResult) -> None:
    for key in ("title", "context", "objective"):
        if not result.introduction.get(key, "").strip():
            raise ValueError(f"Introduction is missing {key}.")
    question_ids = {question.id for question in scenario.questions}
    unknown = set(result.questions) - question_ids
    if unknown:
        raise ValueError(f"Unknown question text ids: {sorted(unknown)}")
    for question in scenario.questions:
        text = result.questions.get(question.id, {}).get("text", question.text)
        explanation = result.questions.get(question.id, {}).get("explanation", question.explanation)
        if not text.strip() or not explanation.strip():
            raise ValueError(f"Question text result is empty for {question.id}.")
        _validate_choices_still_referenced(question, text)


def _base_content_generator(provider: str, model: str) -> ScenarioContentGenerator:
    if provider == "procedural":
        return ProceduralContentGenerator()
    if provider == "local-llm":
        return LocalLLMContentGenerator(model=model)
    raise ValueError(f"Unknown content generation provider: {provider}")


def _world_prompt(seed: int, pack: Pack, difficulty: DifficultyConfig, world: World, model: str) -> str:
    payload = {
        "task": "assistcluedo_world_content",
        "model_hint": model,
        "seed": seed,
        "pack_id": pack.id,
        "difficulty": difficulty.id,
        "instructions": [
            "Generate visible narrative content only; do not change IDs or add/remove entities.",
            "Return JSON only.",
            "Every returned mapping must use exactly the supplied IDs.",
            "Names must be natural, distinct, and suitable for a closed manor investigation.",
            "Public roles, descriptions, object names, location names, and motives must vary with the seed.",
            "Keep each entity compatible with its symbolic type, access, capabilities, and object_type.",
        ],
        "characters": [
            {
                "id": character.id,
                "base_name": character.name,
                "base_public_role": character.public_role,
                "capabilities": character.capabilities,
            }
            for character in world.characters
        ],
        "locations": [
            {
                "id": location.id,
                "base_name": location.name,
                "location_type": location.location_type,
                "access": location.attributes.get("access"),
            }
            for location in world.locations
        ],
        "objects": [
            {
                "id": obj.id,
                "base_name": obj.name,
                "object_type": obj.object_type,
                "location_id": obj.location_id,
            }
            for obj in world.objects
        ],
        "base_motives": pack.motives,
        "required_output": {
            "characters": {"id": {"name": "string", "public_role": "string", "description": "string"}},
            "locations": {"id": {"name": "string", "description": "string"}},
            "objects": {"id": {"name": "string", "description": "string"}},
            "motives": ["string"],
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _scenario_text_prompt(scenario: Scenario, model: str) -> str:
    payload = {
        "task": "assistcluedo_scenario_texts",
        "model_hint": model,
        "seed": scenario.seed,
        "pack_id": scenario.pack_id,
        "difficulty": scenario.difficulty,
        "instructions": [
            "Rewrite only public introduction, question wording, and explanations.",
            "Do not change choice IDs, correct answers, supporting facts, supporting documents, or ground truth.",
            "Questions must remain answerable from the same evidence.",
            "Return JSON only.",
        ],
        "world": {
            "characters": [{"id": item.id, "name": item.name, "role": item.public_role} for item in scenario.world.characters],
            "locations": [{"id": item.id, "name": item.name, "type": item.location_type} for item in scenario.world.locations],
            "objects": [{"id": item.id, "name": item.name, "type": item.object_type} for item in scenario.world.objects],
        },
        "documents": [
            {"id": document.id, "title": document.title, "type": document.visible_metadata.get("type")}
            for document in scenario.documents
        ],
        "questions": [
            {
                "id": question.id,
                "category": question.category,
                "text": question.text,
                "choices": [choice.to_dict() for choice in question.choices],
                "correct_choice_ids": question.correct_choice_ids,
                "supporting_fact_ids": question.supporting_fact_ids,
                "supporting_document_ids": question.supporting_document_ids,
                "explanation": question.explanation,
            }
            for question in scenario.questions
        ],
        "required_output": {
            "introduction": {"title": "string", "context": "string", "objective": "string"},
            "questions": {"question_id": {"text": "string", "explanation": "string"}},
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _validate_entity_texts(label: str, ids: list[str], values: dict[str, dict[str, str]]) -> None:
    expected = set(ids)
    actual = set(values)
    if actual != expected:
        raise ValueError(f"{label} content ids mismatch: expected={sorted(expected)} actual={sorted(actual)}")
    names: list[str] = []
    for entity_id in ids:
        item = values[entity_id]
        name = item.get("name", "").strip()
        description = item.get("description", "").strip()
        if not name or not description:
            raise ValueError(f"{label} {entity_id} has empty generated content.")
        if "_" in name:
            raise ValueError(f"{label} {entity_id} exposes an internal-looking name.")
        if label == "character" and not item.get("public_role", "").strip():
            raise ValueError(f"{label} {entity_id} has empty public role.")
        names.append(name.casefold())
    if len(names) != len(set(names)):
        raise ValueError(f"{label} names must be unique.")


def _validate_choices_still_referenced(question: QuizQuestion, text: str) -> None:
    choice_texts = [choice.text for choice in question.choices]
    if question.category == "ultimate statement":
        return
    if any(choice_text in text for choice_text in choice_texts):
        return


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError("Expected object mapping.")
    return {str(key): str(item) for key, item in value.items()}


def _procedural_role(base_role: str, rng: random.Random) -> str:
    prefix = rng.choice(["reserved", "well-connected", "long-serving", "recently returned", "trusted"])
    return f"{prefix} {base_role}"


def _procedural_character_description(base_role: str, rng: random.Random) -> str:
    detail = rng.choice([
        "known for noticing small breaches of etiquette",
        "carrying private worries behind a calm public manner",
        "often found at the edge of household conversations",
        "careful about reputation and old obligations",
    ])
    return f"A {base_role} {detail}."


def _procedural_location_name(location: Location, rng: random.Random) -> str:
    adjective = rng.choice(["North", "Green", "Old", "East", "Lower", "Panelled", "Winter"])
    return f"{adjective} {location.name}"


def _procedural_location_description(location: Location, rng: random.Random) -> str:
    texture = rng.choice([
        "with a door that carries sound more than anyone admits",
        "kept orderly for guests but used constantly by the household",
        "where lamps leave the corners less clear after dinner",
        "not far from the busier passages of the house",
    ])
    return f"A {location.location_type} space {texture}."


def _procedural_object_name(obj: WorldObject, rng: random.Random) -> str:
    material = rng.choice(["monogrammed", "heavy", "old", "polished", "service", "dark-handled"])
    return f"{material} {obj.name}"


def _procedural_object_description(obj: WorldObject, rng: random.Random) -> str:
    note = rng.choice([
        "usually accounted for during evening checks",
        "ordinary enough to pass unnoticed until it is missing",
        "kept close to its room rather than carried through the house",
        "showing the kind of wear that makes provenance plausible",
    ])
    return f"A {obj.object_type} {note}."


def _procedural_motive(motive: str, rng: random.Random) -> str:
    frame = rng.choice([
        "renewed pressure around",
        "a private quarrel over",
        "fear of exposure involving",
        "resentment sharpened by",
    ])
    return f"{frame} {motive}"
