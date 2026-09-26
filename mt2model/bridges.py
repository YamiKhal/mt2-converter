from dataclasses import dataclass, field

from . import records
from .obstruction import counter_clockwise

Vector = tuple[float, float, float]
Point = tuple[float, float]

BRIDGE_LENGTH = 50.0
DEFAULT_DEPTH = -20.0
REPLACE = "__replace"


@dataclass
class Bridge:
    height: float = 0.0
    ramp_path: list[Vector] = field(default_factory=list)
    obstruction: list[list[Point]] = field(default_factory=list)
    depth: float = DEFAULT_DEPTH
    fully_obstructed: bool = False


def variant_path(theme: str) -> str:
    return f"bridge_themes/{theme}.vrt"


def read_bridge(text: bytes | str) -> Bridge | None:
    variant = _variant(records.parse(text))
    if variant is None:
        return None
    bridge = Bridge(float(variant.prop("height") or 0.0))
    bridge.ramp_path = [_vector(line) for line in _path_lines(variant)]
    sections = variant.child("obstruction")
    for section in sections.children_named("mmoCrossSection") if sections else []:
        vertex = section.child("vertex")
        points = [line.floats() for line in vertex.children] if vertex else []
        bridge.obstruction.append([(p[0], p[2]) for p in points if len(p) >= 3])
        if points:
            bridge.depth = points[0][1]
    bridge.fully_obstructed = (variant.prop("fullyObstructed") or "").lower() == "true"

    return bridge


def set_ramp_path(text: bytes | str, points: list[Vector], replaces_game: bool) -> str:
    parsed = records.parse(text)
    variant = _variant(parsed)
    path = records.block("path", *[records.vector_line(p) for p in points])
    _replace_child(variant, "rampPath", records.block("rampPath", records.block("mmoPadPath", path)))
    variant.set_prop("height", float(points[-1][1]), quoted=False)
    _mark_replace(variant, replaces_game)

    return records.render(parsed)


def set_obstruction(text: bytes | str, polygons: list[list[Point]], fully_obstructed: bool, replaces_game: bool) -> str:
    parsed = records.parse(text)
    variant = _variant(parsed)
    depth = read_bridge(text).depth
    sections = [
        records.block("mmoCrossSection", records.block("vertex", *[records.vector_line((x, depth, z)) for x, z in polygon]))
        for polygon in map(counter_clockwise, polygons)
    ]
    variant.set_prop("fullyObstructed", "true" if fully_obstructed else "false", quoted=False)
    _replace_child(variant, "obstruction", records.block("obstruction", *sections))
    _mark_replace(variant, replaces_game)

    return records.render(parsed)


def _variant(parsed: list[records.Record]) -> records.Record | None:
    return next((r for r in parsed if r.label == "mmoBridgeVariant"), None)


def _path_lines(variant: records.Record) -> list[records.Record]:
    ramp = variant.child("rampPath")
    pad_path = ramp.child("mmoPadPath") if ramp else None
    path = pad_path.child("path") if pad_path else None

    return path.children if path else []


def _vector(line: records.Record) -> Vector:
    values = line.floats()

    return (values[0], values[1], values[2])


def _replace_child(owner: records.Record, label: str, replacement: records.Record):
    index = next((i for i, c in enumerate(owner.children) if c.label == label), None)
    if index is None:
        owner.children.append(replacement)
    else:
        owner.children[index] = replacement


def _mark_replace(variant: records.Record, replaces_game: bool):
    variant.children = [c for c in variant.children if c.label != REPLACE]
    if replaces_game:
        variant.children.insert(0, records.Record(REPLACE, line_open=False))
