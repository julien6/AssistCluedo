from __future__ import annotations

import pytest

from assistcluedo.framework.generator import generate_symbolic_scenario
from assistcluedo.framework.validation import validate_scenario
from assistcluedo.game.exploration_package import build_exploration_package
from assistcluedo.game.player_package import build_player_package

SEEDS = (101, 202, 303, 404, 505)


@pytest.mark.parametrize("seed", SEEDS)
def test_generation_is_valid_and_every_document_has_a_retrieval_location(seed: int) -> None:
    scenario = generate_symbolic_scenario(seed, difficulty="medium")
    report = validate_scenario(scenario)
    assert report.ok, report.issues
    for plan in scenario.document_plans:
        assert plan.retrieval_location_id
        assert not (plan.source_device_id and plan.witness_character_id)


@pytest.mark.parametrize("seed", SEEDS)
def test_exploration_package_covers_every_document_with_a_valid_source(seed: int) -> None:
    scenario = generate_symbolic_scenario(seed, difficulty="medium")
    package = build_exploration_package(scenario)

    location_ids = {location.id for location in package.locations}
    device_ids = {device.id for device in package.devices}
    character_ids = {character.id for character in scenario.world.characters}

    covered_document_ids: set[str] = set()
    for source in package.interactive_sources:
        assert source.location_id in location_ids
        if source.device_id is not None:
            assert source.device_id in device_ids
        if source.character_id is not None:
            assert source.character_id in character_ids
        assert source.document_ids, f"{source.id} has no documents (orphan interactive source)"
        covered_document_ids.update(source.document_ids)

    all_document_ids = {document.id for document in scenario.documents}
    assert covered_document_ids == all_document_ids, "every document must have exactly one physical source"


@pytest.mark.parametrize("seed", SEEDS)
def test_document_mode_and_exploration_mode_expose_the_same_documents(seed: int) -> None:
    scenario = generate_symbolic_scenario(seed, difficulty="medium")
    player_package = build_player_package(scenario)
    exploration_package = build_exploration_package(scenario)

    document_mode_ids = {document.id for document in player_package.documents}
    exploration_mode_ids = {
        document_id
        for source in exploration_package.interactive_sources
        for document_id in source.document_ids
    }
    assert document_mode_ids == exploration_mode_ids
