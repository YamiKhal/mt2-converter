from dataclasses import dataclass, field

from . import records
from .costume import Color

Vector = tuple[float, float, float]


@dataclass
class PartPlacement:
    bone: str
    model_file: str | None = None
    model_scale: float = 1.0
    offset: Vector = (0.0, 0.0, 0.0)
    offset_scale: Vector = (1.0, 1.0, 1.0)


@dataclass
class CostumeFile:
    name: str
    actor: str
    parts: list[PartPlacement] = field(default_factory=list)


def read_costume(text: bytes | str) -> CostumeFile:
    costume = _costume_record(records.parse(text))
    parsed = CostumeFile(costume.prop("name") or "", costume.prop("actorName") or "humanoid")
    for descriptor in _descriptors(costume):
        offset = descriptor.child("boneOffset")
        parsed.parts.append(PartPlacement(
            bone=descriptor.prop("boneName") or "",
            model_file=descriptor.prop("modelFilename"),
            model_scale=float(descriptor.prop("modelScale") or 1.0),
            offset=_vector(offset, "translation", (0.0, 0.0, 0.0)),
            offset_scale=_vector(offset, "scale", (1.0, 1.0, 1.0)),
        ))

    return parsed


def write_costume(template: bytes | str, name: str, parts: list[PartPlacement], actor: str | None = None,
                  renames: dict[str, str] | None = None) -> str:
    parsed = records.parse(template)
    costume = _costume_record(parsed)
    costume.set_prop("name", name)
    if actor is not None:
        costume.set_prop("actorName", actor)
    _rename_descriptors(costume, renames or {})
    by_bone = {p.bone: p for p in parts}
    container = costume.child("costumePart")
    for descriptor in _descriptors(costume):
        part = by_bone.pop(descriptor.prop("boneName") or "", None)
        if part is not None:
            _place(descriptor, part)
        elif descriptor.prop("modelFilename"):
            descriptor.children = [c for c in descriptor.children if c.label != "modelFilename"]
    for part in by_bone.values():
        descriptor = records.block("mmoCostumePartDescriptor", records.leaf("boneName", part.bone, semicolon=False))
        _place(descriptor, part)
        container.children.append(descriptor)

    return records.render(parsed)


def rename_bones(text: bytes | str, renames: dict[str, str]) -> str:
    parsed = records.parse(text)
    _rename_descriptors(_costume_record(parsed), renames)

    return records.render(parsed)


def _rename_descriptors(costume: records.Record, renames: dict[str, str]):
    for descriptor in _descriptors(costume):
        bone = descriptor.prop("boneName") or ""
        if bone in renames:
            descriptor.set_prop("boneName", renames[bone])


def _place(descriptor: records.Record, part: PartPlacement):
    kept = [c for c in descriptor.children if c.label not in ("modelFilename", "modelScale", "boneOffset")]
    bone = [c for c in kept if c.label == "boneName"]
    rest = [c for c in kept if c.label != "boneName"]
    placement = [
        records.leaf("modelFilename", part.model_file, semicolon=False),
        records.leaf("modelScale", part.model_scale, quoted=False),
        records.block("boneOffset",
                      records.Record("translation", records.vector_line(part.offset).tokens, line_open=False),
                      records.Record("scale", records.vector_line(part.offset_scale).tokens, line_open=False)),
    ]
    descriptor.children = bone + placement + rest


def write_defaults(palette: list[Color]) -> str:
    lines = [records.Record(None, [records.Token("text", ",".join(f"{c:.6f}" for c in color))], line_open=False)
             for color in palette[:8]]

    return records.render([records.block("mmoCostumeDefaults", records.block("colors", *lines))])


def _costume_record(parsed: list[records.Record]) -> records.Record:
    costume = next((r for r in parsed if r.label == "mmoCostume"), None)
    if costume is None:
        raise ValueError("not a .costume file: no mmoCostume")

    return costume


def _descriptors(costume: records.Record) -> list[records.Record]:
    container = costume.child("costumePart")

    return container.children_named("mmoCostumePartDescriptor") if container else []


def _vector(owner: records.Record | None, label: str, default: Vector) -> Vector:
    line = owner.child(label) if owner else None
    values = line.floats() if line else []

    return tuple(values[:3]) if len(values) >= 3 else default
