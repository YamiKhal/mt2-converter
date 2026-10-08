from dataclasses import dataclass, field

from . import records

Vector = tuple[float, float, float]


@dataclass
class Entrance:
    name: str
    points: list[Vector] = field(default_factory=list)


@dataclass
class Pad:
    name: str
    corners: list[Vector] = field(default_factory=list)
    entrances: list[Entrance] = field(default_factory=list)


def read_pads(owner: records.Record) -> list[Pad]:
    container = owner.child("pad")
    if container is None:
        return []

    return [_read_pad(r) for r in container.children_named("mmoPad")]


def _read_pad(record: records.Record) -> Pad:
    pad = Pad(record.prop("name") or "")
    cs = record.child("cs")
    vertex = cs.child("vertex") if cs else None
    pad.corners = [c.vector() for c in vertex.children] if vertex else []
    entrances = record.child("entrance")
    for entrance in entrances.children_named("mmoPadEntrance") if entrances else []:
        path = entrance.child("path")
        points = [c.vector() for c in path.children] if path else []
        pad.entrances.append(Entrance(entrance.prop("name") or "", points))

    return pad


def pads_block(pads: list[Pad]) -> records.Record:
    return records.block("pad", *[_pad_record(p) for p in pads])


def _pad_record(pad: Pad) -> records.Record:
    entrances = [
        records.block(
            "mmoPadEntrance",
            records.leaf("name", e.name, semicolon=False),
            records.block("path", *[records.vector_line(p) for p in e.points]),
        )
        for e in pad.entrances
    ]

    return records.block(
        "mmoPad",
        records.leaf("name", pad.name),
        records.block("cs", records.block("vertex", *[records.vector_line(c) for c in pad.corners])),
        records.block("entrance", *entrances),
    )


def replace_pads(owner: records.Record, pads: list[Pad]):
    index = next((i for i, c in enumerate(owner.children) if c.label == "pad"), None)
    if index is None:
        owner.children.append(pads_block(pads))
    else:
        owner.children[index] = pads_block(pads)


def pad_problems(pads: list[Pad]) -> list[tuple[str, str]]:
    problems = []
    for pad in pads:
        if len(pad.corners) != 4:
            problems.append(("warning", f"pad '{pad.name}' has {len(pad.corners)} corners; pads have 4"))
        if not pad.entrances:
            problems.append(("warning", f"pad '{pad.name}' has no entrance, so NPCs may not reach it"))
        for entrance in pad.entrances:
            if not entrance.points:
                problems.append(("warning", f"entrance '{entrance.name}' of pad '{pad.name}' has no points"))

    return problems
