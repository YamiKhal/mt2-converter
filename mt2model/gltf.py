import base64
import json
import math
import struct
from pathlib import Path

from .colors import linear_to_srgb
from .model import Fragment, Node, pack_triangles

COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
FORMATS = {
    5120: ("b", 127.0),
    5121: ("B", 255.0),
    5122: ("h", 32767.0),
    5123: ("H", 65535.0),
    5125: ("I", 1.0),
    5126: ("f", 1.0),
}
IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]

Vector = tuple[float, float, float]


class GltfFile:
    def __init__(self, path: Path):
        self.path = path
        raw = path.read_bytes()
        self.binary = b""
        if raw[:4] == b"glTF":
            self.doc, self.binary = _read_glb(raw)
        else:
            self.doc = json.loads(raw.decode("utf-8"))
        self.buffers = [self._buffer(b) for b in self.doc.get("buffers", [])]

    def _buffer(self, buffer: dict) -> bytes:
        uri = buffer.get("uri")
        if uri is None:
            return self.binary
        if uri.startswith("data:"):
            return base64.b64decode(uri.split(",", 1)[1])

        return (self.path.parent / uri).read_bytes()

    def accessor(self, index: int) -> list[tuple[float, ...]]:
        accessor = self.doc["accessors"][index]
        count, width = accessor["count"], COMPONENTS[accessor["type"]]
        code, scale = FORMATS[accessor["componentType"]]
        if "bufferView" not in accessor:
            return [(0.0,) * width] * count
        view = self.doc["bufferViews"][accessor["bufferView"]]
        data = self.buffers[view["buffer"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        size = struct.calcsize(code)
        stride = view.get("byteStride") or size * width
        normalize = accessor.get("normalized", False) or (code in "bBhH" and accessor["type"] != "SCALAR")
        values = []
        for i in range(count):
            item = struct.unpack_from(f"<{width}{code}", data, start + i * stride)
            values.append(tuple(v / scale for v in item) if normalize else tuple(float(v) for v in item))

        return values


def _read_glb(raw: bytes) -> tuple[dict, bytes]:
    doc, binary, offset = {}, b"", 12
    while offset < len(raw):
        length, kind = struct.unpack_from("<II", raw, offset)
        chunk = raw[offset + 8 : offset + 8 + length]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        offset += 8 + length

    return doc, binary


def convert(path: Path, height: float | None = None) -> Node:
    gltf = GltfFile(path)
    triangles: list[tuple] = []
    scene = gltf.doc.get("scenes", [{}])[gltf.doc.get("scene", 0)] if gltf.doc.get("scenes") else {}
    roots = scene.get("nodes", list(range(len(gltf.doc.get("nodes", [])))))
    for index in roots:
        _walk(gltf, index, IDENTITY, triangles)
    triangles = _ground(triangles, height)

    return Node(name="RootNode", lods=[_fragments(triangles)])


def _walk(gltf: GltfFile, index: int, parent: list[float], out: list):
    node = gltf.doc["nodes"][index]
    world = _multiply(parent, _local(node))
    if "mesh" in node:
        for primitive in gltf.doc["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", 4) == 4:
                out += _primitive(gltf, primitive, world)
    for child in node.get("children", []):
        _walk(gltf, child, world, out)


def _local(node: dict) -> list[float]:
    if "matrix" in node:
        return [float(v) for v in node["matrix"]]
    tx, ty, tz = node.get("translation", (0.0, 0.0, 0.0))
    qx, qy, qz, qw = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    sx, sy, sz = node.get("scale", (1.0, 1.0, 1.0))
    r = [
        1 - 2 * (qy * qy + qz * qz),
        2 * (qx * qy + qz * qw),
        2 * (qx * qz - qy * qw),
        2 * (qx * qy - qz * qw),
        1 - 2 * (qx * qx + qz * qz),
        2 * (qy * qz + qx * qw),
        2 * (qx * qz + qy * qw),
        2 * (qy * qz - qx * qw),
        1 - 2 * (qx * qx + qy * qy),
    ]

    return [
        r[0] * sx,
        r[1] * sx,
        r[2] * sx,
        0.0,
        r[3] * sy,
        r[4] * sy,
        r[5] * sy,
        0.0,
        r[6] * sz,
        r[7] * sz,
        r[8] * sz,
        0.0,
        tx,
        ty,
        tz,
        1.0,
    ]


def _multiply(a: list[float], b: list[float]) -> list[float]:
    return [sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4)) for col in range(4) for row in range(4)]


def _apply(m: list[float], p, w: float) -> Vector:
    return tuple(m[row] * p[0] + m[4 + row] * p[1] + m[8 + row] * p[2] + m[12 + row] * w for row in range(3))


def _primitive(gltf: GltfFile, primitive: dict, world: list[float]) -> list[tuple]:
    attributes = primitive["attributes"]
    positions = [_to_game(_apply(world, p, 1.0)) for p in gltf.accessor(attributes["POSITION"])]
    normals = (
        [_to_game(_normalized(_apply(world, n, 0.0))) for n in gltf.accessor(attributes["NORMAL"])]
        if "NORMAL" in attributes
        else None
    )
    colors = gltf.accessor(attributes["COLOR_0"]) if "COLOR_0" in attributes else None
    base = _base_color(gltf, primitive.get("material"))
    indices = (
        [int(i[0]) for i in gltf.accessor(primitive["indices"])]
        if "indices" in primitive
        else list(range(len(positions)))
    )
    triangles = []
    for k in range(0, len(indices) - 2, 3):
        a, b, c = indices[k], indices[k + 2], indices[k + 1]
        face = _face_normal(positions[a], positions[b], positions[c])
        if face is None:
            continue
        triangle = []
        for i in (a, b, c):
            color = colors[i] if colors else (1.0, 1.0, 1.0, 1.0)
            color = tuple(color) + (1.0,) * (4 - len(color))
            tinted = tuple(color[j] * base[j] for j in range(4))
            srgb = linear_to_srgb(tinted)
            normal = normals[i] if normals else face
            triangle.append(positions[i] + srgb + normal)
        triangles.append(triangle)

    return triangles


def _to_game(p) -> Vector:
    return (-p[0], p[1], -p[2])


def _normalized(v) -> Vector:
    length = math.sqrt(sum(x * x for x in v)) or 1.0

    return tuple(x / length for x in v)


def _face_normal(a, b, c) -> Vector | None:
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(x * x for x in n))

    return tuple(-x / length for x in n) if length > 1e-12 else None


def _base_color(gltf: GltfFile, material: int | None) -> tuple[float, ...]:
    if material is None:
        return (1.0, 1.0, 1.0, 1.0)
    pbr = gltf.doc["materials"][material].get("pbrMetallicRoughness", {})

    return tuple(pbr.get("baseColorFactor", (1.0, 1.0, 1.0, 1.0)))


def _ground(triangles: list, height: float | None) -> list:
    points = [v[:3] for t in triangles for v in t]
    if not points:
        return triangles
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    size = high[1] - low[1]
    factor = height / size if height and size > 0 else 1.0
    base = ((low[0] + high[0]) / 2, low[1], (low[2] + high[2]) / 2)

    return [[tuple((v[i] - base[i]) * factor for i in range(3)) + tuple(v[3:]) for v in t] for t in triangles]


def _fragments(triangles: list) -> list[Fragment]:
    rounded = [[tuple(round(x, 6) for x in v) for v in triangle] for triangle in triangles]

    return pack_triangles("Material_tint", "PCN", rounded)
