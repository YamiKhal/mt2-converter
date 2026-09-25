from . import records
from .footprint import area

Point = tuple[float, float]


def obs_file_name(model_file_name: str) -> str:
    stem = model_file_name[:-4] if model_file_name.lower().endswith(".vmb") else model_file_name

    return f"{stem}_obs.vrt"


def write_obstruction(polygons: list[list[Point]]) -> str:
    sections = [
        records.block("mmoCrossSection", records.block("vertex", *[records.vector_line((x, 0.0, z)) for x, z in poly]))
        for poly in map(counter_clockwise, polygons)
    ]

    return records.render([records.block("mmoObstructionData", records.block("obs", *sections))])


def counter_clockwise(polygon: list[Point]) -> list[Point]:
    return list(polygon) if area(polygon) >= 0 else list(reversed(polygon))


def read_obstruction(text: str) -> list[list[Point]]:
    data = next((r for r in records.parse(text) if r.label == "mmoObstructionData"), None)
    obs = data.child("obs") if data else None
    if obs is None:
        return []
    polygons = []
    for section in obs.children_named("mmoCrossSection"):
        vertex = section.child("vertex")
        points = [c.floats() for c in vertex.children] if vertex else []
        polygons.append([(p[0], p[2]) for p in points if len(p) >= 3])

    return polygons
