from .formats import layout
from .model import Node


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
