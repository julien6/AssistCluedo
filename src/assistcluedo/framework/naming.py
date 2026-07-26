from __future__ import annotations

from assistcluedo.framework.models import World


def entity_name(world: World, entity_id: str) -> str:
    for collection in (world.characters, world.locations, world.objects):
        for item in collection:
            if item.id == entity_id:
                return item.name
    return entity_id

