from __future__ import annotations

import random
from typing import Any

from assistcluedo.framework.difficulty import DifficultyConfig
from assistcluedo.framework.models import (
    Character,
    Location,
    Relationship,
    TravelEdge,
    World,
    WorldObject,
)
from assistcluedo.framework.pack import Pack
from assistcluedo.framework.seed import rng_for


class WorldGenerator:
    def generate(self, seed: int, pack: Pack, difficulty: DifficultyConfig) -> World:
        rng = rng_for(seed, "world")
        selected_characters = _select_required_plus_random(
            pack.characters,
            ["general", "head_chef", "butler", "doctor", "niece", "gardener"],
            difficulty.characters,
            rng,
        )
        selected_locations = _select_required_plus_random(
            pack.locations,
            ["entrance_hall", "kitchen", "pantry", "dining_room", "office", "library"],
            difficulty.locations,
            rng,
        )
        location_ids = {str(item["id"]) for item in selected_locations}
        selected_objects = [item for item in pack.objects if str(item["location_id"]) in location_ids]
        characters = [
            Character(
                id=str(item["id"]),
                name=str(item["name"]),
                public_role=str(item["public_role"]),
                private_role=None,
                capabilities=[str(capability) for capability in item.get("capabilities", [])],
                relationship_ids=[],
            )
            for item in selected_characters
        ]
        locations = [
            Location(
                id=str(item["id"]),
                name=str(item["name"]),
                location_type=str(item["location_type"]),
                parent_id="manor",
                attributes={"access": str(item.get("access", "public"))},
            )
            for item in selected_locations
        ]
        objects = [
            WorldObject(
                id=str(item["id"]),
                name=str(item["name"]),
                object_type=str(item["object_type"]),
                location_id=str(item["location_id"]),
                owner_id=None,
                attributes={"can_be_weapon": True},
            )
            for item in selected_objects
        ]
        rival = rng.choice([char.id for char in characters if char.id != "general"])
        relationships = [
            Relationship(
                id="rel_general_rival",
                source_character_id=rival,
                target_character_id="general",
                relationship_type="resentment",
                attributes={"public": False},
            )
        ]
        travel_edges = _travel_edges_for(pack, locations)
        return World(
            id=pack.id,
            characters=characters,
            locations=locations,
            objects=objects,
            relationships=relationships,
            travel_edges=travel_edges,
        )


def _select_required_plus_random(
    items: list[dict[str, Any]], required_ids: list[str], count: int, rng: random.Random
) -> list[dict[str, Any]]:
    required = [item for item in items if str(item["id"]) in required_ids]
    remaining = [item for item in items if str(item["id"]) not in required_ids]
    remaining.sort(key=lambda item: str(item["id"]))
    rng.shuffle(remaining)
    return (required + remaining)[:count]


def _travel_edges_for(pack: Pack, locations: list[Location]) -> list[TravelEdge]:
    location_ids = {location.id for location in locations}
    edges: list[TravelEdge] = []
    for source, target, minutes in pack.travel_edges:
        if source in location_ids and target in location_ids:
            edges.append(TravelEdge(source, target, minutes))
            edges.append(TravelEdge(target, source, minutes))
    if not edges:
        return [
            TravelEdge(source.id, target.id, 1)
            for source in locations
            for target in locations
            if source.id != target.id
        ]
    edges = _connect_selected_subgraph(edges, location_ids)
    return edges


def _connect_selected_subgraph(edges: list[TravelEdge], location_ids: set[str]) -> list[TravelEdge]:
    adjacency: dict[str, set[str]] = {location_id: set() for location_id in location_ids}
    for edge in edges:
        adjacency[edge.source_location_id].add(edge.target_location_id)
    anchor = "entrance_hall" if "entrance_hall" in location_ids else min(location_ids)
    seen = {anchor}
    stack = [anchor]
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    missing = sorted(location_ids - seen)
    for location_id in missing:
        edges.append(TravelEdge(anchor, location_id, 4))
        edges.append(TravelEdge(location_id, anchor, 4))
    return edges
