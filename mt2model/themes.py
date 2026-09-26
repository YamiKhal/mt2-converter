import re
from dataclasses import dataclass

from . import model, records
from .gamedata import GameData
from .recolor import remap_colors

Color = tuple[float, float, float, float]
PROP_FOLDER = "scenery/tagged/"


@dataclass(frozen=True)
class ThemeFamily:
    key: str
    label: str
    folder: str
    conf: str | None


FAMILIES = {
    f.key: f
    for f in (
        ThemeFamily("dungeon", "Dungeon", "dungeon/themes", "theme.conf"),
        ThemeFamily("building", "Modular building", "building_themes", "theme.conf"),
        ThemeFamily("wall", "Wall", "wall_themes", None),
        ThemeFamily("bridge", "Bridge", "bridge_themes", None),
    )
}


def theme_names(data: GameData, family: str) -> list[str]:
    folder = FAMILIES[family].folder + "/"
    names = {rel[len(folder):].split("/", 1)[0] for rel in data.files(folder) if rel.count("/") > folder.count("/")}

    return sorted(n for n in names if data.files(f"{folder}{n}/"))


def copy_theme(data: GameData, family: str, source: str, name: str, colors: list[Color] | None = None) -> dict[str, bytes]:
    theme = FAMILIES[family]
    prefix = f"{theme.folder}/{source}/"
    files = {}
    for rel in data.files(prefix):
        tail = _rename(rel[len(prefix):], source, name)
        content = data.read(rel)
        if theme.conf and tail == theme.conf:
            content = _theme_conf(content, name, colors).encode("latin-1")
        files[f"{theme.folder}/{name}/{tail}"] = content
    sibling = f"{theme.folder}/{source}.vrt"
    if family == "bridge" and data.exists(sibling):
        files[f"{theme.folder}/{name}.vrt"] = _bridge_variant(data.read(sibling), source, name).encode("latin-1")
    if family == "dungeon":
        diorama = f"{theme.folder}/{name}/diorama_{name}.vmb"
        old_colors = read_colors(data.read(f"{prefix}{theme.conf}")) if data.exists(f"{prefix}{theme.conf}") else []
        if colors and old_colors and diorama in files:
            root = model.read_model(files[diorama])
            remap_colors(root, old_colors, colors)
            files[diorama] = model.write_model(root)
        files.update(theme_props(data, source, name))

    return files


# The dungeon only places props whose file name has its theme's name as a tag, so a new theme needs copies.
def theme_props(data: GameData, source: str, name: str) -> dict[str, bytes]:
    props = {}
    for rel in data.files(PROP_FOLDER, ".vmb"):
        tags = rel[len(PROP_FOLDER):-len(".vmb")].split("_")
        if source in tags:
            renamed = "_".join(name if tag == source else tag for tag in tags)
            props[f"{PROP_FOLDER}{renamed}.vmb"] = data.read(rel)

    return props


def _rename(path: str, source: str, name: str) -> str:
    return re.sub(rf"(?<=[_/]){re.escape(source)}(?=[_.])|^{re.escape(source)}(?=[_.])", name, path)


def _theme_conf(template: bytes, name: str, colors: list[Color] | None) -> str:
    parsed = records.parse(template)
    theme = parsed[0]
    theme.set_prop("directory", name)
    theme.set_prop("displayName", name)
    if colors:
        lines = [records.Record(None, [records.Token("text", ",".join(f"{c:.6f}" for c in color))], line_open=False)
                 for color in colors[:4]]
        index = next((i for i, c in enumerate(theme.children) if c.label == "colors"), None)
        if index is not None:
            theme.children[index] = records.block("colors", *lines)

    return records.render(parsed)


def _bridge_variant(template: bytes, source: str, name: str) -> str:
    parsed = records.parse(template)
    variant = parsed[0]
    variant.set_prop("name", name)
    for field in ("rampFile", "bridgeFile"):
        value = variant.prop(field)
        if value:
            variant.set_prop(field, _rename(value.replace(f"/{source}/", f"/{name}/"), source, name))

    return records.render(parsed)


def read_colors(text: bytes | str) -> list[Color]:
    theme = next((r for r in records.parse(text) if r.label == "mmoDungeonTheme"), None)
    colors = theme.child("colors") if theme else None
    values = [tuple(c.floats()[:4]) for c in colors.children] if colors else []

    return [v + (1.0,) * (4 - len(v)) for v in values][:4]
