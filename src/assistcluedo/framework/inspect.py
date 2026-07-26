from __future__ import annotations

from collections import Counter
from pathlib import Path

from assistcluedo.framework.export import load_exported_scenario
from assistcluedo.framework.models import Scenario
from assistcluedo.framework.validation import validate_export, validate_scenario


def inspect_export(path: Path, include_oracle: bool = False) -> str:
    scenario = load_exported_scenario(path)
    export_report = validate_export(path)
    scenario_report = validate_scenario(scenario)
    lines = [
        f"Scenario: {scenario.id}",
        f"Seed: {scenario.seed}",
        f"Pack: {scenario.pack_id}@{scenario.pack_version}",
        f"Difficulty: {scenario.difficulty}",
        f"Validation: {'OK' if export_report.ok and scenario_report.ok else 'FAILED'}",
        "",
        "World",
        f"- Characters: {len(scenario.world.characters)}",
        f"- Locations: {len(scenario.world.locations)}",
        f"- Objects: {len(scenario.world.objects)}",
        f"- Travel edges: {len(scenario.world.travel_edges)}",
        "",
        "Player Package",
        f"- Documents: {len(scenario.documents)}",
        f"- Quiz questions: {len(scenario.questions)}",
    ]
    doc_types = Counter(str(document.visible_metadata.get("type", "unknown")) for document in scenario.documents)
    lines.extend(f"  - {doc_type}: {count}" for doc_type, count in sorted(doc_types.items()))
    question_categories = Counter(question.category for question in scenario.questions)
    lines.append("- Question categories:")
    lines.extend(f"  - {category}: {count}" for category, count in sorted(question_categories.items()))
    lines.extend(["", "Public Characters"])
    lines.extend(f"- {char.name}: {char.public_role}" for char in scenario.world.characters)
    lines.extend(["", "Public Locations"])
    lines.extend(f"- {loc.name} ({loc.location_type})" for loc in scenario.world.locations)
    if include_oracle:
        lines.extend(["", "Oracle"])
        lines.extend(_oracle_lines(scenario))
    return "\n".join(lines)


def _oracle_lines(scenario: Scenario) -> list[str]:
    truth = scenario.ground_truth
    name = {char.id: char.name for char in scenario.world.characters}
    loc = {location.id: location.name for location in scenario.world.locations}
    obj = {item.id: item.name for item in scenario.world.objects}
    return [
        f"- Culprit: {name[truth.culprit_id]}",
        f"- Victim: {name[truth.victim_id]}",
        f"- Location: {loc[truth.location_id]}",
        f"- Weapon: {obj[truth.weapon_id]}",
        f"- Motive: {truth.motive}",
        f"- Incident time: {truth.incident_time.isoformat()}",
    ]

