from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Pack:
    id: str
    version: str
    title: str
    setting_name: str
    characters: list[dict[str, Any]]
    locations: list[dict[str, Any]]
    objects: list[dict[str, Any]]
    motives: list[str]
    document_titles: dict[str, str]
    travel_edges: list[tuple[str, str, int]]


def default_pack_root() -> Path:
    packaged_root = Path(__file__).resolve().parents[1] / "scenario_packs"
    if packaged_root.exists():
        return packaged_root
    return Path(__file__).resolve().parents[3] / "scenario_packs"


def load_pack(pack_id: str = "classic_manor", pack_root: Path | None = None) -> Pack:
    root = pack_root or default_pack_root()
    pack_path = root / pack_id / "pack.yaml"
    if not pack_path.exists():
        raise ValueError(f"Scenario pack not found: {pack_path}")
    data = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    return Pack(
        id=str(data["id"]),
        version=str(data["version"]),
        title=str(data["title"]),
        setting_name=str(data["setting_name"]),
        characters=list(data["characters"]),
        locations=list(data["locations"]),
        objects=list(data["objects"]),
        motives=[str(item) for item in data["motives"]],
        document_titles={str(key): str(value) for key, value in data["document_titles"].items()},
        travel_edges=[
            (str(source), str(target), int(minutes))
            for source, target, minutes in data.get("travel_edges", [])
        ],
    )
