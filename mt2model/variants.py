from dataclasses import dataclass

from . import records
from .gamedata import GameData
from .pads import Pad, replace_pads


@dataclass(frozen=True)
class BuildingKind:
    name: str
    key: str
    directory: str


def building_kinds(data: GameData) -> list[BuildingKind]:
    kinds = []
    for rel in data.files("buildings/definitions/", ".def"):
        for record in records.parse(data.read(rel)):
            directory = record.prop("variantDirectory")
            if record.label == "mmoBuildingDefinition" and directory:
                kinds.append(BuildingKind(record.prop("name") or "", record.prop("key") or "", directory))

    return sorted(kinds, key=lambda k: k.name)


def gizmo_dirs(data: GameData) -> list[str]:
    dirs = set()
    for rel in data.files("gizmo/definition/", ".def"):
        for record in records.parse(data.read(rel)):
            directory = record.prop("variantDirectory")
            if record.label == "mmoGizmoDefinition" and directory:
                dirs.add(directory.rstrip("/"))

    return sorted(dirs)


def variant_files(data: GameData, directory: str) -> list[str]:
    return [n for n in data.files(directory.rstrip("/") + "/", ".variant") if n.count("/") == directory.count("/") + 1]


def variant_for_model(data: GameData, model_rel: str) -> str | None:
    directory = model_rel.rsplit("/", 1)[0]
    for rel in variant_files(data, directory):
        variant = _variant_record(data.read(rel))
        if variant is not None and variant.prop("modelFile") == model_rel:
            return rel

    return None


def derive_variant(source_text: bytes | str, name: str, model_rel: str, pads: list[Pad] | None = None,
                   label: str = "mmoBuildingVariant") -> str:
    parsed = records.parse(source_text)
    variant = next((r for r in parsed if r.label == label), None)
    if variant is None:
        raise ValueError(f"the source file has no {label}")
    variant.set_prop("name", name)
    variant.set_prop("modelFile", model_rel)
    if pads is not None:
        replace_pads(variant, pads)

    return records.render(parsed)


@dataclass(frozen=True)
class Creature:
    costume: str
    animation: str = "idle"
    offset: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float, float] | None = None


def read_creature(variant_text: bytes | str) -> Creature | None:
    variant = _variant_record(variant_text)
    if variant is None or not variant.prop("actor"):
        return None
    offset = variant.child("actorOffset")
    rotation = variant.child("actorRotation")

    return Creature(variant.prop("actor"), variant.prop("actorAnimation") or "idle",
                    tuple(offset.floats()[:3]) if offset and len(offset.floats()) >= 3 else None,
                    tuple(rotation.floats()[:4]) if rotation and len(rotation.floats()) >= 4 else None)


def set_creature(variant_text: bytes | str, creature: Creature) -> str:
    parsed = records.parse(variant_text)
    variant = next((r for r in parsed if r.prop("modelFile")), None)
    if variant is None:
        raise ValueError("the variant has no modelFile")
    variant.set_prop("actor", creature.costume)
    variant.set_prop("actorAnimation", creature.animation)
    if creature.offset is not None:
        variant.set_prop("actorOffset", *creature.offset, quoted=False)
    if creature.rotation is not None:
        variant.set_prop("actorRotation", *creature.rotation, quoted=False)

    return records.render(parsed)


def display_name_key(kind_key: str, variant_name: str) -> str:
    return f"building_variant_{kind_key}_{variant_name}_displayname"


def _variant_record(text: bytes | str) -> records.Record | None:
    return next((r for r in records.parse(text) if r.prop("modelFile")), None)
