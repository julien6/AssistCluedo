from __future__ import annotations

from assistcluedo.framework.models import Character, Location, World

ACCESS_CAPABILITIES = {
    "public": set(),
    "hall": set(),
    "service": {"access_service_rooms", "access_all_rooms"},
    "office": {"access_office", "access_all_rooms"},
    "garage": {"access_garage", "access_all_rooms"},
    "grounds": {"access_grounds", "access_all_rooms"},
}


def character_can_access_location(character: Character, location: Location) -> bool:
    access_tag = str(location.attributes.get("access", location.location_type))
    required = ACCESS_CAPABILITIES.get(access_tag, set())
    return not required or bool(set(character.capabilities) & required)


def accessible_location_ids(character: Character, world: World) -> set[str]:
    return {
        location.id
        for location in world.locations
        if character_can_access_location(character, location)
    }

