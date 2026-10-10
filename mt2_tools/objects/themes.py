import bpy

from ..mt2model.gamedata import GameData
from ..mt2model.themes import ASSET_FAMILIES, FAMILIES, ModTheme, mod_themes

_cache: dict = {"names": None, "themes": []}


def themes_in_mod(data: GameData | None) -> list[ModTheme]:
    if data is None:
        return []
    names = data.overlay_names()
    if _cache["names"] is not names:
        _cache["names"] = names
        _cache["themes"] = mod_themes(names)

    return _cache["themes"]


def theme_field(asset: str) -> str:
    return "dungeon_theme" if asset == "dungeon_tile" else "theme"


def from_theme_file(root: bpy.types.Object) -> bool:
    s = root.mt2
    family = ASSET_FAMILIES.get(s.asset)
    if family is None:
        return False
    theme = getattr(s, theme_field(s.asset))

    return bool(theme) and s.source_path.startswith(f"{FAMILIES[family].folder}/{theme}/")
