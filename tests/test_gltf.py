import json
import struct
import tempfile
import unittest
from pathlib import Path

from mt2model.gltf import convert


def _glb(positions, colors) -> bytes:
    binary = b"".join(struct.pack("<3f", *p) for p in positions) + b"".join(struct.pack("<4f", *c) for c in colors)
    doc = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "translation": [0, 5, 0]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "COLOR_0": 1}}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                        {"buffer": 0, "byteOffset": 36, "byteLength": 48}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                      {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC4"}],
    }
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(binary), 0x004E4942) + binary

    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


class GltfTests(unittest.TestCase):
    def test_triangle_becomes_a_grounded_clockwise_fragment(self):
        path = Path(tempfile.mkdtemp()) / "t.glb"
        path.write_bytes(_glb([(0, 0, 0), (1, 0, 0), (0, 2, 0)], [(1, 0, 0, 1)] * 3))
        root = convert(path, height=4.0)
        fragment = root.fragments[0]

        self.assertEqual((fragment.material, fragment.format), ("Material_tint", "PCN"))
        points = [v[:3] for v in fragment.vertices]
        self.assertAlmostEqual(min(p[1] for p in points), 0.0)
        self.assertAlmostEqual(max(p[1] for p in points), 4.0)
        a, b, c = (fragment.vertices[i] for i in fragment.indices)
        u = [b[i] - a[i] for i in range(3)]
        w = [c[i] - a[i] for i in range(3)]
        cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        self.assertLess(sum(x * n for x, n in zip(cross, a[7:10])), 0)
        self.assertAlmostEqual(a[3], 1.0)


if __name__ == "__main__":
    unittest.main()
