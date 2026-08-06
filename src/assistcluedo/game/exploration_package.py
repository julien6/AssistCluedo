from __future__ import annotations

from dataclasses import dataclass, field

from assistcluedo.framework.models import Scenario


@dataclass(frozen=True)
class ExplorationLocation:
    id: str
    name: str
    location_type: str

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "locationType": self.location_type}


@dataclass(frozen=True)
class ExplorationTravelEdge:
    from_location_id: str
    to_location_id: str
    travel_minutes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "fromLocationId": self.from_location_id,
            "toLocationId": self.to_location_id,
            "travelMinutes": self.travel_minutes,
        }


@dataclass(frozen=True)
class ExplorationDevice:
    id: str
    name: str
    device_type: str
    location_id: str
    owner_character_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "deviceType": self.device_type,
            "locationId": self.location_id,
            "ownerCharacterId": self.owner_character_id,
        }


@dataclass(frozen=True)
class InteractiveSource:
    id: str
    source_type: str
    location_id: str
    document_ids: list[str] = field(default_factory=list)
    device_id: str | None = None
    character_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sourceType": self.source_type,
            "locationId": self.location_id,
            "documentIds": self.document_ids,
            "deviceId": self.device_id,
            "characterId": self.character_id,
        }


@dataclass(frozen=True)
class ExplorationPackage:
    locations: list[ExplorationLocation]
    travel_edges: list[ExplorationTravelEdge]
    devices: list[ExplorationDevice]
    interactive_sources: list[InteractiveSource]

    def to_dict(self) -> dict[str, object]:
        return {
            "locations": [item.to_dict() for item in self.locations],
            "travelEdges": [item.to_dict() for item in self.travel_edges],
            "devices": [item.to_dict() for item in self.devices],
            "interactiveSources": [item.to_dict() for item in self.interactive_sources],
        }


def build_exploration_package(scenario: Scenario) -> ExplorationPackage:
    world = scenario.world
    locations = [
        ExplorationLocation(id=location.id, name=location.name, location_type=location.location_type)
        for location in world.locations
    ]
    travel_edges = [
        ExplorationTravelEdge(edge.source_location_id, edge.target_location_id, edge.travel_minutes)
        for edge in world.travel_edges
    ]
    devices = [
        ExplorationDevice(
            id=device.id,
            name=device.name,
            device_type=device.device_type,
            location_id=device.location_id,
            owner_character_id=device.owner_character_id,
        )
        for device in world.devices
    ]

    plan_by_id = {plan.id: plan for plan in scenario.document_plans}
    grouped: dict[str, InteractiveSource] = {}
    order: list[str] = []
    for document in scenario.documents:
        plan = plan_by_id.get(document.plan_id)
        if plan is None:
            continue
        if plan.source_device_id is not None:
            key = f"device:{plan.source_device_id}"
            source_type = "device"
        elif plan.witness_character_id is not None:
            key = f"character:{plan.witness_character_id}"
            source_type = "character"
        else:
            key = f"physical:{plan.retrieval_location_id}:{plan.author_id or 'misc'}"
            source_type = "physical-object"
        if key not in grouped:
            order.append(key)
            grouped[key] = InteractiveSource(
                id=key,
                source_type=source_type,
                location_id=plan.retrieval_location_id,
                device_id=plan.source_device_id,
                character_id=plan.witness_character_id,
            )
        grouped[key].document_ids.append(document.id)

    return ExplorationPackage(
        locations=locations,
        travel_edges=travel_edges,
        devices=devices,
        interactive_sources=[grouped[key] for key in order],
    )
