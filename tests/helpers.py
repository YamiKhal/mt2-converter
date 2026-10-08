import os
import tempfile
from pathlib import Path

from mt2model import detect
from mt2model.gamedata import GameData
from mt2model.model import Fragment, Node

TINT_MAT = 'Material {\n\tmode lit\n\tshader "tint_v.glsl" "tint_f.glsl"\n}\n'
COSTUME_MAT = 'Material {\n\tmode lit\n\tshader "costume_v.glsl" "costume_f.glsl"\n}\n'
TEXTURED_MAT = 'Material {\n\tmode lit\n\ttexture "a.png"\n\tshader "tint_v.glsl" "tint_f.glsl"\n}\n'


def fake_game() -> GameData:
    root = Path(tempfile.mkdtemp())
    (root / "materials").mkdir()
    (root / "materials" / "Material_tint.mat").write_text(TINT_MAT)
    (root / "materials" / "costume.mat").write_text(COSTUME_MAT)
    (root / "materials" / "crate.mat").write_text(TEXTURED_MAT)

    return GameData.open(root)


def real_game() -> GameData | None:
    game = os.environ.get("MT2_GAME") or detect.find_game()

    return GameData.open(game) if game else None


def cube(material: str = "Material_tint", fmt: str = "PCN", size: float = 1.0, lift: float = 0.0) -> Node:
    corners = [(x, y + lift, z) for x in (-size, size) for y in (0.0, 2 * size) for z in (-size, size)]
    extra = {
        "PCN": (0.5, 0.5, 0.5, 1.0, 0.0, 1.0, 0.0),
        "PNT": (0.0, 1.0, 0.0, 0.0625, 0.2),
        "PN": (0.0, 1.0, 0.0),
        "PCNT": (0.5, 0.5, 0.5, 1.0, 0.0, 1.0, 0.0, 0.1, 0.1),
    }[fmt]
    vertices = [c + extra for c in corners]
    faces = [
        (0, 1, 3),
        (0, 3, 2),
        (4, 6, 7),
        (4, 7, 5),
        (0, 4, 5),
        (0, 5, 1),
        (2, 3, 7),
        (2, 7, 6),
        (0, 2, 6),
        (0, 6, 4),
        (1, 5, 7),
        (1, 7, 3),
    ]

    return Node(lods=[[Fragment(material, fmt, vertices, [i for f in faces for i in f])]])
