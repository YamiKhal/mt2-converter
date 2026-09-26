from collections.abc import Callable

from . import records

SECTIONS = ("buildings", "walls", "bridges", "modularBuildings", "scenery", "costumes", "weaponCategories", "vehicles")
ART_SECTIONS = tuple(s for s in SECTIONS if s != "weaponCategories")
WEAPON_PACK_PREFIX = "artpacks/weapons_"


def pack_content(paths: list[str], is_vanilla_folder: Callable[[str], bool]) -> dict[str, list[str]]:
    content: dict[str, set[str]] = {section: set() for section in SECTIONS}
    themes = {"building_themes": "modularBuildings", "wall_themes": "walls", "bridge_themes": "bridges"}
    for rel in paths:
        parts = rel.split("/")
        if parts[0] == "scenery" and len(parts) == 3 and parts[1] != "tagged":
            content["scenery"].add(f"{parts[1]}/{parts[2]}")
        elif parts[0] == "buildings" and len(parts) == 3 and rel.endswith(".vmb"):
            content["buildings"].add(rel)
        elif parts[0] == "costumes" and len(parts) == 2 and rel.endswith(".costume"):
            content["costumes"].add(parts[1][: -len(".costume")])
        elif parts[0] == "weapons" and len(parts) == 3 and not is_vanilla_folder(f"weapons/{parts[1]}/"):
            content["weaponCategories"].add(parts[1])
        elif parts[0] in themes and len(parts) >= 3 and not is_vanilla_folder(f"{parts[0]}/{parts[1]}/"):
            content[themes[parts[0]]].add(parts[1])
        elif parts[0] == "vehicles" and len(parts) == 3 and rel.endswith(".vmb"):
            content["vehicles"].add(parts[2][: -len(".vmb")])

    return {section: sorted(items) for section, items in content.items()}


def art_pack(key: str, cost: int, exotic: bool, content: dict[str, list[str]]) -> str:
    sections = [records.block(section, *[records.leaf(None, item) for item in content.get(section, [])])
                for section in ART_SECTIONS]

    return _pack("art", key, cost, exotic, sections)


def weapon_pack(category: str, cost: int) -> str:
    return _pack("weapons", category, cost, False, [records.block("weaponCategories", records.leaf(None, category))])


def weapon_pack_path(category: str) -> str:
    return f"{WEAPON_PACK_PREFIX}{category}.vrt"


def _pack(kind: str, key: str, cost: int, exotic: bool, sections: list[records.Record]) -> str:
    body = [records.leaf("type", kind), records.leaf("key", key)]
    if cost > 0:
        body.append(records.leaf("cost", cost, quoted=False))
    if exotic:
        body.append(records.leaf("exotic", "true", quoted=False))
    body.append(records.block("content", *sections))

    return records.render([records.block("mmoArtPack", *body)])


def is_empty(content: dict[str, list[str]]) -> bool:
    return not any(content.get(section) for section in ART_SECTIONS)
