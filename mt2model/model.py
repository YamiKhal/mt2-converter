from dataclasses import dataclass, field
from pathlib import Path

from .binary import Reader, Writer
from .formats import layout


@dataclass
class Fragment:
    material: str
    format: str
    vertices: list[tuple[float, ...]] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)


@dataclass
class Node:
    name: str = "RootNode"
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    lods: list[list[Fragment]] = field(default_factory=lambda: [[]])
    children: list["Node"] = field(default_factory=list)
    version: str = "ModelV1"

    @property
    def fragments(self) -> list[Fragment]:
        return self.lods[0] if self.lods else []

    def walk(self, depth: int = 0):
        yield self, depth
        for child in self.children:
            yield from child.walk(depth + 1)


VERSIONS = ("ModelV1", "ModelV2")


def _read_fragment(r: Reader) -> Fragment:
    tag = r.string()
    if tag != "Fragment":
        raise ValueError(f"expected 'Fragment', found {tag!r}")
    material = r.string()
    fmt = r.string()
    size = layout(fmt).size
    count = r.int32()
    flat = r.floats(count * size)
    vertices = [flat[i:i + size] for i in range(0, len(flat), size)]
    tag = r.string()
    if tag != "IndexBuffer":
        raise ValueError(f"expected 'IndexBuffer', found {tag!r}")
    indices = list(r.int32s(r.int32()))

    return Fragment(material, fmt, vertices, indices)


def _read_node(r: Reader) -> Node:
    version = r.string()
    if version not in VERSIONS:
        raise ValueError(f"expected a model header, found {version!r}")
    node = Node(name=r.string(), version=version)
    node.translation = r.floats(3)
    node.rotation = r.floats(4)
    node.scale = r.floats(3)
    if version == "ModelV1":
        node.lods = [[_read_fragment(r) for _ in range(r.int32())]]
    else:
        node.lods = [[_read_fragment(r) for _ in range(r.int32())] for _ in range(r.int32())]
    node.children = [_read_node(r) for _ in range(r.int32())]

    return node


def read_model(data: bytes) -> Node:
    return read_model_with_size(data)[0]


def read_model_with_size(data: bytes) -> tuple[Node, int]:
    r = Reader(data)
    node = _read_node(r)

    return node, r.pos


def _write_fragment(w: Writer, fragment: Fragment):
    w.string("Fragment")
    w.string(fragment.material)
    w.string(fragment.format)
    w.int32(len(fragment.vertices))
    w.floats([value for vertex in fragment.vertices for value in vertex])
    w.string("IndexBuffer")
    w.int32(len(fragment.indices))
    w.int32s(fragment.indices)


def _write_node(w: Writer, node: Node):
    w.string(node.version)
    w.string(node.name)
    w.floats(list(node.translation))
    w.floats(list(node.rotation))
    w.floats(list(node.scale))
    if node.version == "ModelV1":
        fragments = node.lods[0] if node.lods else []
        w.int32(len(fragments))
        for fragment in fragments:
            _write_fragment(w, fragment)
    else:
        w.int32(len(node.lods))
        for lod in node.lods:
            w.int32(len(lod))
            for fragment in lod:
                _write_fragment(w, fragment)
    w.int32(len(node.children))
    for child in node.children:
        _write_node(w, child)


def write_model(node: Node) -> bytes:
    w = Writer()
    _write_node(w, node)

    return w.bytes()


def load(path: str | Path) -> Node:
    return read_model(Path(path).read_bytes())


def save(node: Node, path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(write_model(node))
