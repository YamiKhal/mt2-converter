from . import records
from .formats import layout
from .model import Node

Color = tuple[float, float, float, float]

GREY_PALETTE: list[Color] = [(g, g, g, 1.0) for g in (0.9, 0.75, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)]


def read_defaults(text: bytes | str) -> list[Color]:
    defaults = next((r for r in records.parse(text) if r.label == "mmoCostumeDefaults"), None)
    colors = defaults.child("colors") if defaults else None
    if colors is None:
        return list(GREY_PALETTE)
    palette = [tuple(c.floats()[:4]) for c in colors.children if len(c.floats()) >= 3]
    palette = [p + (1.0,) * (4 - len(p)) for p in palette]

    return (palette + GREY_PALETTE)[:8]


def extent(root: Node) -> float:
    points = [v[:3] for node, _ in root.walk() for f in node.fragments for v in f.vertices]
    if not points:
        return 0.0

    return max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))


def normalise(root: Node) -> float:
    size = extent(root)
    if size <= 0:
        return 1.0
    for node, _ in root.walk():
        for fragment in node.fragments:
            n = layout(fragment.format).size
            fragment.vertices = [tuple(x / size for x in v[:3]) + tuple(v[3:n]) for v in fragment.vertices]

    return size


def slot_u(slot: int, slots: int = 8) -> float:
    return (slot + 0.5) / slots


def slot_of(u: float, slots: int = 8) -> int:
    return int(u * slots) % slots
