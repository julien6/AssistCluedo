from __future__ import annotations

from datetime import UTC, datetime, timedelta
from heapq import heappop, heappush

from assistcluedo.framework.access import accessible_location_ids
from assistcluedo.framework.difficulty import DifficultyConfig
from assistcluedo.framework.models import Event, Fact, GroundTruth, World
from assistcluedo.framework.seed import rng_for


class TimelineEngine:
    def generate(
        self,
        seed: int,
        world: World,
        truth: GroundTruth,
        difficulty: DifficultyConfig,
    ) -> list[Event]:
        rng = rng_for(seed, "timeline")
        base = datetime(2026, 8, 9, 19, 30, tzinfo=UTC)
        all_chars = sorted(char.id for char in world.characters)
        characters_by_id = {char.id: char for char in world.characters}
        other_chars = [
            char_id for char_id in all_chars if char_id not in {truth.culprit_id, truth.victim_id}
        ]
        argument_location = (
            "office"
            if "office" in accessible_location_ids(characters_by_id[truth.false_lead_character_id], world)
            else "dining_room"
        )
        hide_location = _hide_location_for(characters_by_id[truth.culprit_id], world, truth.location_id)
        discoverer_id = _discoverer_for(world, truth)
        # The alibi witness must be someone with no other role in the timeline's tightly scripted
        # events (not the culprit, victim, false lead, exculpated character, discoverer, or
        # doctor) so their single "I saw them there" appointment can't collide with a fixed event
        # elsewhere. This mirrors `critical_actors`/`available_actors` below, computed early
        # because the alibi event needs to exist before that later block runs.
        critical_actors = {
            truth.culprit_id,
            truth.false_lead_character_id,
            truth.exculpated_character_id,
            discoverer_id,
            "doctor",
            truth.victim_id,
        }
        strictly_free_actors = sorted(char.id for char in world.characters if char.id not in critical_actors)
        available_actors = strictly_free_actors or sorted(
            char.id for char in world.characters if char.id != truth.victim_id
        )
        # A fully free actor (no other scripted role) is the ideal alibi witness — nothing else
        # ties up their schedule. When the cast is too small for one to exist (every character is
        # already cast in a critical role), fall back to a lightly-scripted role whose own fixed
        # events sit comfortably away from the alibi's timestamp, rather than the raw "everyone
        # but the victim" pool (`available_actors`'s own fallback, used below for contextual
        # filler events), which would risk picking the culprit or exculpated character themselves.
        alibi_witness_candidates = [
            char_id for char_id in strictly_free_actors if char_id != truth.exculpated_character_id
        ]
        if not alibi_witness_candidates:
            alibi_witness_candidates = [
                char_id
                for char_id in {truth.false_lead_character_id, discoverer_id, "doctor"}
                if char_id not in {truth.culprit_id, truth.victim_id, truth.exculpated_character_id}
                and char_id in characters_by_id
            ]
        if not alibi_witness_candidates:
            alibi_witness_candidates = [
                char_id
                for char_id in other_chars
                if char_id != truth.exculpated_character_id
            ]
        if not alibi_witness_candidates:
            alibi_witness_candidates = [
                char_id for char_id in all_chars if char_id != truth.exculpated_character_id
            ]
        alibi_witness_id = rng.choice(sorted(alibi_witness_candidates))
        exculpated_location = _exculpating_location_for(
            characters_by_id[truth.exculpated_character_id],
            world,
            truth.location_id,
            co_witness=characters_by_id[alibi_witness_id],
        )
        alibi_time = truth.incident_time - timedelta(minutes=5)
        # Same self-reference problem as the alibi witness: the false statement is about the
        # false-lead character, so whoever is interviewed about it must not be the false lead
        # themselves. Unlike the alibi, this event carries no location, so no location-access
        # check is needed for the witness.
        false_statement_witness_candidates = [
            char_id for char_id in strictly_free_actors if char_id != truth.false_lead_character_id
        ]
        if not false_statement_witness_candidates:
            false_statement_witness_candidates = [
                char_id
                for char_id in {truth.culprit_id, truth.exculpated_character_id, discoverer_id, "doctor"}
                if char_id not in {truth.false_lead_character_id, truth.victim_id}
                and char_id in characters_by_id
            ]
        if not false_statement_witness_candidates:
            false_statement_witness_candidates = [
                char_id for char_id in other_chars if char_id != truth.false_lead_character_id
            ]
        if not false_statement_witness_candidates:
            false_statement_witness_candidates = [
                char_id for char_id in all_chars if char_id != truth.false_lead_character_id
            ]
        false_statement_witness_id = rng.choice(sorted(false_statement_witness_candidates))
        false_statement_time = truth.incident_time + timedelta(minutes=18)
        events = [
            Event("ev_001", "arrive", all_chars, [], "dining_room", base, None, [], {}),
            Event(
                "ev_002",
                "argument",
                [truth.false_lead_character_id, truth.victim_id],
                [],
                argument_location,
                base.replace(hour=20, minute=5),
                None,
                [],
                {"topic": "money"},
            ),
            Event(
                "ev_003",
                "send_sms",
                [truth.culprit_id],
                [truth.victim_id],
                None,
                base.replace(hour=20, minute=27),
                None,
                [],
                {"message": "Meet me where nobody will interrupt us."},
            ),
            Event(
                "ev_004",
                "badge_access",
                [truth.culprit_id],
                [],
                truth.location_id,
                truth.incident_time - timedelta(minutes=11),
                None,
                [],
                {},
            ),
            Event(
                "ev_005",
                "camera_disabled",
                [truth.culprit_id],
                [],
                truth.location_id,
                truth.incident_time - timedelta(minutes=7),
                truth.incident_time + timedelta(minutes=15),
                [],
                {},
            ),
            Event(
                "ev_006",
                "move",
                [truth.exculpated_character_id],
                [],
                exculpated_location,
                alibi_time,
                None,
                [],
                {},
            ),
            Event(
                "ev_006_alibi_witness",
                "witness_observe_alibi",
                [alibi_witness_id],
                [truth.exculpated_character_id],
                exculpated_location,
                alibi_time,
                None,
                [],
                {},
            ),
            Event(
                "ev_007",
                "main_incident",
                [truth.culprit_id],
                [truth.victim_id],
                truth.location_id,
                truth.incident_time,
                None,
                [truth.weapon_id],
                {"motive": truth.motive},
            ),
            Event(
                "ev_008",
                "hide_evidence",
                [truth.culprit_id],
                [],
                hide_location,
                truth.incident_time + timedelta(minutes=8),
                None,
                [truth.weapon_id],
                {},
            ),
            Event(
                "ev_009",
                "witness_observe",
                [rng.choice(other_chars)],
                [truth.culprit_id],
                "entrance_hall",
                truth.incident_time + timedelta(minutes=11),
                None,
                [],
                {},
            ),
            Event(
                "ev_010",
                "false_statement",
                [truth.false_lead_character_id],
                [],
                None,
                false_statement_time,
                None,
                [],
                {"claim": "I saw nothing after dinner."},
            ),
            Event(
                "ev_010_false_statement_witness",
                "witness_observe_false_statement",
                [false_statement_witness_id],
                [truth.false_lead_character_id],
                None,
                false_statement_time,
                None,
                [],
                {},
            ),
            Event(
                "ev_011",
                "discover_body",
                [discoverer_id],
                [truth.victim_id],
                truth.location_id,
                truth.incident_time + timedelta(minutes=23),
                None,
                [],
                {},
            ),
            Event(
                "ev_012",
                "autopsy",
                ["doctor"],
                [truth.victim_id],
                "library",
                truth.incident_time + timedelta(hours=11),
                None,
                [],
                {},
            ),
        ]
        event_kinds = ["call", "receipt", "gps_ping", "staff_round", "door_check", "conversation"]
        travel_minutes = _shortest_travel_minutes(world)
        per_actor_last = {
            actor_id: (event.start_time, event.location_id)
            for event in events
            if event.location_id is not None
            for actor_id in event.actor_ids
        }
        occupied = {
            (actor_id, event.start_time): event.location_id
            for event in events
            for actor_id in event.actor_ids
        }
        for offset in range(difficulty.contextual_events):
            actor = rng.choice(available_actors)
            actor_accessible = sorted(
                accessible_location_ids(characters_by_id[actor], world) - {truth.location_id}
            )
            if not actor_accessible:
                actor_accessible = sorted(loc.id for loc in world.locations if loc.id != truth.location_id)
            location = rng.choice(actor_accessible)
            minute = 35 + (offset * 7) % 120
            if base.replace(hour=20, minute=minute % 60) == truth.incident_time:
                minute += 2
            hour = 19 + minute // 60
            event_time = base.replace(hour=hour, minute=minute % 60)
            last = per_actor_last.get(actor)
            if last is not None:
                last_time, last_location = last
                required = travel_minutes.get((last_location, location), 0)
                earliest = last_time + timedelta(minutes=required)
                event_time = max(event_time, earliest)
            while (actor, event_time) in occupied and occupied[(actor, event_time)] != location:
                event_time += timedelta(minutes=1)
            occupied[(actor, event_time)] = location
            per_actor_last[actor] = (event_time, location)
            events.append(
                Event(
                    id=f"ev_ctx_{offset + 1:03d}",
                    event_type=event_kinds[offset % len(event_kinds)],
                    actor_ids=[actor],
                    target_ids=[],
                    location_id=location,
                    start_time=event_time,
                    end_time=None,
                    object_ids=[],
                    attributes={"contextual": True},
                )
            )
        events.sort(key=lambda event: (event.start_time, event.id))
        return events


class FactEngine:
    def generate(self, world: World, truth: GroundTruth, events: list[Event]) -> list[Fact]:
        event_by_type = {event.event_type: event for event in events}
        facts = [
            Fact(
                "fact_culprit_identity",
                "culprit",
                "is",
                truth.culprit_id,
                truth.incident_time,
                truth.location_id,
                True,
            ),
            Fact(
                "fact_victim_identity",
                "victim",
                "is",
                truth.victim_id,
                truth.incident_time,
                truth.location_id,
                True,
            ),
            Fact(
                "fact_murder_location",
                "incident",
                "location",
                truth.location_id,
                truth.incident_time,
                truth.location_id,
                True,
            ),
            Fact(
                "fact_murder_weapon",
                "incident",
                "weapon",
                truth.weapon_id,
                truth.incident_time,
                truth.location_id,
                True,
            ),
            Fact(
                "fact_weapon_initial_location",
                truth.weapon_id,
                "initially_at",
                truth.location_id,
                None,
                truth.location_id,
                True,
            ),
            Fact("fact_motive", truth.culprit_id, "motive", truth.motive, None, None, True),
            Fact(
                "fact_sms_meeting",
                truth.culprit_id,
                "summoned",
                truth.victim_id,
                event_by_type["send_sms"].start_time,
                None,
                True,
            ),
            Fact(
                "fact_badge_access",
                truth.culprit_id,
                "entered",
                truth.location_id,
                event_by_type["badge_access"].start_time,
                truth.location_id,
                True,
            ),
            Fact(
                "fact_camera_disabled",
                "camera",
                "disabled_at",
                truth.location_id,
                event_by_type["camera_disabled"].start_time,
                truth.location_id,
                True,
            ),
            Fact(
                "fact_exculpated_alibi",
                truth.exculpated_character_id,
                "was_at",
                event_by_type["move"].location_id,
                event_by_type["move"].start_time,
                event_by_type["move"].location_id,
                True,
            ),
            Fact(
                "fact_false_lead_argument",
                truth.false_lead_character_id,
                "argued_with",
                truth.victim_id,
                event_by_type["argument"].start_time,
                event_by_type["argument"].location_id,
                True,
            ),
            Fact(
                "fact_false_statement",
                truth.false_lead_character_id,
                "denied_activity",
                truth.location_id,
                event_by_type["false_statement"].start_time,
                truth.location_id,
                False,
            ),
            Fact(
                "fact_witness_seen_culprit",
                truth.culprit_id,
                "seen_leaving",
                truth.location_id,
                event_by_type["witness_observe"].start_time,
                "entrance_hall",
                True,
            ),
            Fact(
                "fact_death_window",
                truth.victim_id,
                "died_between",
                f"{truth.incident_time:%H:%M}-{truth.incident_time + timedelta(minutes=8):%H:%M}",
                truth.incident_time,
                truth.location_id,
                True,
            ),
            Fact(
                "fact_weapon_hidden",
                truth.weapon_id,
                "hidden_in",
                event_by_type["hide_evidence"].location_id,
                event_by_type["hide_evidence"].start_time,
                event_by_type["hide_evidence"].location_id,
                True,
            ),
        ]
        for event in events:
            if not event.attributes.get("contextual"):
                continue
            facts.append(
                Fact(
                    id=f"fact_{event.id}",
                    subject=event.actor_ids[0],
                    predicate=f"context_{event.event_type}",
                    object=event.location_id,
                    time=event.start_time,
                    location_id=event.location_id,
                    polarity=True,
                )
            )
        return facts


def _hide_location_for(culprit, world: World, incident_location_id: str) -> str:
    accessible = sorted(accessible_location_ids(culprit, world) - {incident_location_id})
    travel = _shortest_travel_minutes(world)
    reachable = [
        location_id
        for location_id in accessible
        if travel.get((incident_location_id, location_id), 999) <= 8
    ]
    accessible = reachable or accessible
    for preferred in ("pantry", "servants_hall", "entrance_hall", "library", "dining_room"):
        if preferred in accessible:
            return preferred
    return accessible[0] if accessible else incident_location_id


def _exculpating_location_for(
    character, world: World, incident_location_id: str, co_witness=None
) -> str:
    accessible = accessible_location_ids(character, world) - {incident_location_id}
    if co_witness is not None:
        shared = accessible & accessible_location_ids(co_witness, world)
        # Fall back to the character's own accessible set if nothing is shared (should not
        # happen given public/hall rooms require no capability), so a location is always chosen.
        accessible = shared or accessible
    accessible = sorted(accessible)
    if not accessible:
        return incident_location_id
    travel = _shortest_travel_minutes(world)
    return max(accessible, key=lambda location_id: (travel.get((location_id, incident_location_id), 0), location_id))


def _discoverer_for(world: World, truth: GroundTruth) -> str:
    excluded = {truth.culprit_id, truth.victim_id}
    candidates = [
        character
        for character in world.characters
        if character.id not in excluded and truth.location_id in accessible_location_ids(character, world)
    ]
    if not candidates:
        candidates = [character for character in world.characters if character.id != truth.victim_id]
    return min(candidates, key=lambda character: character.id).id


def _shortest_travel_minutes(world: World) -> dict[tuple[str, str], int]:
    location_ids = {loc.id for loc in world.locations}
    graph: dict[str, list[tuple[str, int]]] = {location_id: [] for location_id in location_ids}
    for edge in world.travel_edges:
        if edge.source_location_id in location_ids and edge.target_location_id in location_ids:
            graph[edge.source_location_id].append((edge.target_location_id, edge.travel_minutes))
    distances: dict[tuple[str, str], int] = {}
    for source in location_ids:
        queue: list[tuple[int, str]] = [(0, source)]
        best = {source: 0}
        while queue:
            current_distance, current = heappop(queue)
            if current_distance != best[current]:
                continue
            for target, minutes in graph[current]:
                next_distance = current_distance + minutes
                if target not in best or next_distance < best[target]:
                    best[target] = next_distance
                    heappush(queue, (next_distance, target))
        for target, minutes in best.items():
            distances[(source, target)] = minutes
    return distances
