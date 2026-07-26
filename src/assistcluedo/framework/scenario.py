from __future__ import annotations

from datetime import UTC, datetime, timedelta

from assistcluedo.framework.access import accessible_location_ids
from assistcluedo.framework.models import GroundTruth, World
from assistcluedo.framework.pack import Pack
from assistcluedo.framework.seed import rng_for


class ScenarioGenerator:
    def generate_ground_truth(self, seed: int, world: World, pack: Pack) -> GroundTruth:
        rng = rng_for(seed, "scenario")
        suspects = sorted(char.id for char in world.characters if char.id != "general")
        culprit_id = rng.choice(suspects)
        false_leads = [char_id for char_id in suspects if char_id != culprit_id]
        false_lead_character_id = rng.choice(false_leads)
        exculpated = [char_id for char_id in false_leads if char_id != false_lead_character_id]
        exculpated_character_id = rng.choice(exculpated)
        culprit = next(character for character in world.characters if character.id == culprit_id)
        accessible_locations = accessible_location_ids(culprit, world)
        accessible_weapons = [
            obj for obj in world.objects if obj.location_id in accessible_locations
        ]
        if not accessible_weapons:
            raise ValueError(f"No accessible weapon for culprit {culprit_id}.")
        weapon = rng.choice(sorted(accessible_weapons, key=lambda item: item.id))
        motive = rng.choice(sorted(pack.motives))
        incident_time = datetime(2026, 8, 9, 21, 14, tzinfo=UTC) + timedelta(
            minutes=rng.choice([0, 3, 6, 9])
        )
        return GroundTruth(
            culprit_id=culprit_id,
            victim_id="general",
            location_id=weapon.location_id or "kitchen",
            weapon_id=weapon.id,
            motive=motive,
            incident_time=incident_time,
            false_lead_character_id=false_lead_character_id,
            exculpated_character_id=exculpated_character_id,
        )
