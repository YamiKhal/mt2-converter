from dataclasses import dataclass

from . import records
from .gamedata import GameData


@dataclass(frozen=True)
class MaterialInfo:
    name: str
    kind: str
    textured: bool
    texture: str | None = None


PALETTE_SLOTS = {"costume": 8, "dungeon": 4}

NON_RENDER = {"light": "light", "obstruction": "obstruction", "collision": "collision", "navmesh": "navmesh"}


def classify(name: str, text: str) -> MaterialInfo:
    if name in NON_RENDER:
        return MaterialInfo(name, NON_RENDER[name], False)
    material = next((r for r in records.parse(text) if r.label == "Material"), None)
    if material is None:
        return MaterialInfo(name, "vertex", False)
    shader = material.child("shader")
    shader_files = " ".join(shader.texts()) if shader else ""
    textured = _texture_before_shader(material)
    texture_record = material.child("texture")
    texture = texture_record.texts()[0] if texture_record and texture_record.texts() else None
    if "costume" in shader_files:
        kind = "costume"
    elif "dungeon_" in shader_files or "dungeonceiling" in shader_files:
        kind = "dungeon"
    else:
        kind = "vertex"

    return MaterialInfo(name, kind, textured, texture)


def _texture_before_shader(material: records.Record) -> bool:
    for child in material.children:
        if child.label == "shader":
            return False
        if child.label == "texture":
            return True

    return False


class MaterialCatalog:
    def __init__(self, data: GameData):
        self.data = data
        self._cache: dict[str, MaterialInfo | None] = {}
        self._lower_names: set[str] | None = None

    def names(self) -> set[str]:
        return self.data.materials()

    def get(self, name: str) -> MaterialInfo | None:
        if name not in self._cache:
            self._cache[name] = self._load(name)

        return self._cache[name]

    def file_exists(self, rel: str) -> bool:
        if self._lower_names is None:
            self._lower_names = {n.lower() for n in self.data.names()}

        return rel.replace("\\", "/").lower() in self._lower_names

    def _load(self, name: str) -> MaterialInfo | None:
        rel = f"materials/{name}.mat"
        if not self.data.exists(rel):
            return None

        return classify(name, self.data.read(rel).decode("latin-1"))
