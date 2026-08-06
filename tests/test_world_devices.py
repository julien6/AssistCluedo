from __future__ import annotations

from assistcluedo.framework.difficulty import get_difficulty
from assistcluedo.framework.pack import load_pack
from assistcluedo.framework.world import WorldGenerator


def test_every_selected_character_gets_exactly_one_phone() -> None:
    pack = load_pack("classic_manor")
    world = WorldGenerator().generate(42, pack, get_difficulty("medium"))
    phone_owner_ids = [
        device.owner_character_id for device in world.devices if device.device_type == "phone"
    ]
    character_ids = [character.id for character in world.characters]
    assert sorted(phone_owner_ids) == sorted(character_ids)
    assert len(phone_owner_ids) == len(set(phone_owner_ids))


def test_devices_are_always_located_inside_the_selected_world() -> None:
    pack = load_pack("classic_manor")
    location_ids = {loc["id"] for loc in pack.locations}
    for seed in (1, 2, 3, 4, 5):
        for difficulty_id in ("easy", "medium", "hard", "spark"):
            world = WorldGenerator().generate(seed, pack, get_difficulty(difficulty_id))
            selected_location_ids = {location.id for location in world.locations}
            for device in world.devices:
                assert device.location_id in selected_location_ids
                assert device.location_id in location_ids


def test_institutional_devices_exist_even_when_their_home_room_is_not_selected() -> None:
    pack = load_pack("classic_manor")
    # "easy" only ever selects the 6 required locations, never security_office/archive.
    world = WorldGenerator().generate(7, pack, get_difficulty("easy"))
    selected_location_ids = {location.id for location in world.locations}
    assert "security_office" not in selected_location_ids
    assert "archive" not in selected_location_ids
    device_types = {device.device_type for device in world.devices}
    assert {"badge-reader", "camera-system", "archive-cabinet", "computer"} <= device_types


def test_every_character_has_a_current_location_inside_the_selected_world() -> None:
    pack = load_pack("classic_manor")
    world = WorldGenerator().generate(11, pack, get_difficulty("easy"))
    selected_location_ids = {location.id for location in world.locations}
    for character in world.characters:
        assert character.current_location_id in selected_location_ids
