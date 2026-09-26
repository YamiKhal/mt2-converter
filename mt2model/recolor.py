from .formats import layout
from .model import Node

Color = tuple[float, ...]


def remap_colors(root: Node, old: list[Color], new: list[Color]):
    pairs = list(zip(old, new))
    for node, _ in root.walk():
        for fragment in node.fragments:
            at = layout(fragment.format).color
            if at is None or not pairs:
                continue
            fragment.vertices = [_remapped(v, at, pairs) for v in fragment.vertices]


def _remapped(vertex: tuple[float, ...], at: int, pairs: list[tuple[Color, Color]]) -> tuple[float, ...]:
    rgb = vertex[at:at + 3]
    source, target = min(pairs, key=lambda pair: sum((a - b) ** 2 for a, b in zip(rgb, pair[0][:3])))
    shaded = tuple(min(1.0, c * t / max(s, 0.02)) for c, s, t in zip(rgb, source[:3], target[:3]))

    return vertex[:at] + shaded + vertex[at + 3:]
