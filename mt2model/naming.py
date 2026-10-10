import re
from dataclasses import dataclass, field

from .assets import MODULAR_SLOTS, PLACEABLE_SCENERY_TYPES, TAG_PLACES
from .dungeons import tile_path


@dataclass
class ExportTarget:
    asset: str
    name: str
    mod_id: str
    scenery_type: str = "stone"
    weapon_category: str = "swords"
    item_level: int = 15
    costume_set: str = ""
    bone: str = "head"
    theme: str = ""
    slot: str = "sides"
    building_dir: str = "buildings/tavern"
    wall_piece: str = "wall"
    tag_place: str = "floor"
    tag_kind: str = "prop"
    tag_small: bool = False
    tag_extra: list[str] = field(default_factory=list)
    raw_path: str = ""
    vehicle_kind: str = "air"
    gizmo_dir: str = "gizmo/container"
    dungeon_theme: str = ""
    tile_kind: str = "walls"
    shape: str = "N"
    bridge_piece: str = "bridge"


_MOD_ID = re.compile(r"^[a-z][a-z0-9_]{1,23}$")
_WORD = re.compile(r"^[a-z0-9_]+$")


def mod_id_problem(mod_id: str) -> str | None:
    if not _MOD_ID.match(mod_id) or mod_id.endswith("_") or "__" in mod_id:
        return (
            f"mod id '{mod_id}' must be 2-24 characters of a-z, 0-9 and _, "
            "start with a letter, not end with _ or contain __"
        )

    return None


def clean_word(text: str) -> str:
    word = re.sub(r"[^a-z0-9_]+", "_", text.strip().lower())

    return re.sub(r"_+", "_", word).strip("_")


def prefixed(mod_id: str, name: str) -> str:
    name = clean_word(name)
    if name == mod_id or name.startswith(mod_id + "_"):
        return name

    return f"{mod_id}_{name}"


def model_path(t: ExportTarget) -> str:
    stem = prefixed(t.mod_id, t.name)
    if t.asset == "scenery":
        return f"scenery/{t.scenery_type}/{stem}.vmb"
    if t.asset == "tagged":
        return f"scenery/tagged/{tagged_stem(t, stem)}.vmb"
    if t.asset == "weapon":
        return f"weapons/{t.weapon_category}/{t.item_level:03d}_{stem}.vmb"
    if t.asset == "building":
        return f"{t.building_dir.rstrip('/')}/{stem}.vmb"
    if t.asset == "modular":
        piece = clean_word(t.name) if is_mod_theme(t.mod_id, t.theme) else stem
        return f"building_themes/{t.theme}/{t.slot}/{piece}.vmb"
    if t.asset == "wall":
        return f"wall_themes/{t.theme}/{t.wall_piece}_{t.theme}.vmb"
    if t.asset == "costume_part":
        return f"costumes/{t.costume_set}/{t.bone}.vmb"
    if t.asset == "bridge":
        return f"bridge_themes/{t.theme}/{t.bridge_piece}_{t.theme}.vmb"
    if t.asset == "dungeon_tile":
        return tile_path(t.dungeon_theme, t.tile_kind, t.shape)
    if t.asset == "gizmo":
        return f"{t.gizmo_dir.rstrip('/')}/{stem}.vmb"
    if t.asset == "vehicle":
        return f"vehicles/{t.vehicle_kind}/{stem}.vmb"
    if t.asset == "costume":
        return f"costumes/{stem}.costume"

    return t.raw_path


def is_mod_theme(mod_id: str, theme: str) -> bool:
    return theme == mod_id or theme.startswith(mod_id + "_")


def dungeon_theme_name(mod_id: str, name: str) -> str:
    return (mod_id + clean_word(name)).replace("_", "")


def tagged_stem(t: ExportTarget, stem: str) -> str:
    words = [TAG_PLACES[t.tag_place], t.tag_kind]
    if t.tag_small:
        words.append("small")
    words += [clean_word(w) for w in t.tag_extra if clean_word(w)]

    return "_".join(words + [stem])


def target_problems(t: ExportTarget) -> list[str]:
    problems = []
    if t.asset != "raw":
        problem = mod_id_problem(t.mod_id)
        if problem:
            problems.append(problem)
        if not clean_word(t.name):
            problems.append("the model needs a name")
    if t.asset == "scenery" and t.scenery_type not in PLACEABLE_SCENERY_TYPES:
        problems.append(f"'{t.scenery_type}' is not a scenery type; the game only loads its 46 placeable types")
    if t.asset == "weapon":
        if not _WORD.match(t.weapon_category or ""):
            problems.append("weapon category must be a folder name of a-z, 0-9 and _")
        if not 0 <= t.item_level <= 999:
            problems.append("item level must be between 0 and 999")
    if t.asset == "costume_part" and not _WORD.match(t.costume_set or ""):
        problems.append("costume set must be a folder name of a-z, 0-9 and _")
    if t.asset == "dungeon_tile" and not _WORD.match(t.dungeon_theme or ""):
        problems.append("pick a theme, or make one with New theme")
    if t.asset in ("modular", "wall", "bridge") and not _WORD.match(t.theme or ""):
        problems.append("pick a theme, or make one with New theme")
    if t.asset == "modular" and t.slot not in MODULAR_SLOTS:
        problems.append(f"'{t.slot}' is not a modular piece slot")
    if t.asset == "wall" and t.wall_piece not in ("wall", "turret"):
        problems.append("wall piece must be 'wall' or 'turret'")
    if t.asset == "raw" and not (t.raw_path.endswith(".vmb") and not t.raw_path.startswith("/")):
        problems.append("raw export needs a relative path ending in .vmb")

    return problems
