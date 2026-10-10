from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from .. import game
from ..conversion import to_blender
from ..mt2model import model, records
from ..mt2model.assets import guess_from_path
from ..mt2model.bridges import read_bridge, variant_path
from ..mt2model.dungeons import SHAPES, read_sockets
from ..mt2model.obstruction import obs_file_name, read_obstruction
from ..mt2model.pads import read_pads
from ..mt2model.variants import read_creature, variant_for_model
from ..objects.animation import import_animations
from ..objects.bridges import import_bridge_data
from ..objects.costumes import MESH_HASH_KEY, import_costume, mesh_hash
from ..objects.creature_spot import create_spot, is_flight_point
from ..objects.obstructions import create_obstruction_shape
from ..objects.pads import create_pads
from ..objects.rigs import game_animations
from ..objects.selection import select_only
from ..objects.sockets import create_sockets
from ..properties import building_dir_items, gizmo_dir_items

TOP_FOLDERS = (
    "scenery",
    "weapons",
    "costumes",
    "building_themes",
    "wall_themes",
    "buildings",
    "bridge_themes",
    "vehicles",
    "gizmo",
    "dungeon",
    "portals",
    "depots",
    "docks",
    "skeletons",
)

REFERENCES = (
    ("buildings/tavern/base.vmb", "Tavern", "A vanilla tavern"),
    ("buildings/inn/base.vmb", "Inn", "A vanilla inn"),
    ("scenery/tree/p_ext_tree_01.vmb", "Tree", "A vanilla tree"),
    ("scenery/chair/bench_a.vmb", "Bench", "A vanilla bench"),
    ("weapons/swords/015_sword_basic1.vmb", "Sword", "A vanilla sword, in hand space"),
    ("building_themes/castle2/sides/b_w_castle2_blank.vmb", "Modular wall piece", "One 3 x 3 x 3 cell wall piece"),
    ("wall_themes/castle/wall_castle.vmb", "Wall segment", "A 50 unit wall segment"),
    ("costumes/knight/head.vmb", "Costume head", "A normalised costume part"),
)

_game_items: list = []
_search_spot: list[int] = []


def game_relative(path: str) -> str:
    parts = Path(path).as_posix().split("/")
    for index, part in enumerate(parts):
        if part in TOP_FOLDERS:
            return "/".join(parts[index:])

    return parts[-1]


def import_bytes(context, raw: bytes, rel: str, collection=None) -> bpy.types.Object:
    data = game.game_data()
    collection = collection or context.collection
    stem = rel.rsplit("/", 1)[-1][:-4]
    obj = to_blender.import_model(model.read_model(raw), stem, game.catalog(), collection)
    _describe(obj, rel, stem)
    if data is not None:
        _import_obstruction(obj, rel, data, collection)
        if obj.mt2.asset == "building":
            obj.mt2.source_variant = variant_for_model(data, rel) or ""
            _import_pads(obj, data, obj.mt2.source_variant, collection)
            if is_flight_point(obj) and obj.mt2.source_variant:
                _import_creature(obj, data, obj.mt2.source_variant, collection)
        if obj.mt2.asset == "gizmo":
            obj.mt2.source_variant = variant_for_model(data, rel) or ""
            _import_gizmo(obj, data, collection)
        if obj.mt2.asset == "dungeon_tile" and data.exists(rel[: -len(".vmb")] + ".vrt"):
            create_sockets(obj, read_sockets(data.read(rel[: -len(".vmb")] + ".vrt")), collection)
        if obj.mt2.asset == "bridge":
            _import_bridge(obj, data, collection)
        if obj.mt2.asset == "vehicle" and data.exists(rel[: -len(".vmb")] + ".def"):
            obj.mt2.source_variant = rel[: -len(".vmb")] + ".def"
            _import_pads(obj, data, obj.mt2.source_variant, collection)

    return obj


def _describe(obj, rel: str, stem: str):
    s = obj.mt2
    s.is_asset = True
    s.asset = guess_from_path(rel)
    s.source_path = rel
    s.name = stem
    s.normalise = False
    parts = rel.split("/")
    if s.asset == "scenery":
        s.scenery_type = parts[1]
    elif s.asset == "weapon":
        s.weapon_category = parts[1]
        level, _, rest = stem.partition("_")
        if level.isdigit():
            s.item_level = int(level)
            s.name = rest
    elif s.asset == "costume_part":
        s.costume_set, s.bone = parts[1], stem
    elif s.asset == "modular":
        s.theme, s.slot = parts[1], parts[2]
    elif s.asset == "wall":
        s.theme = parts[1]
        s.wall_piece = "turret" if stem.startswith("turret") else "wall"
    elif s.asset == "building":
        if "/".join(parts[:2]) in {item[0] for item in building_dir_items()}:
            s.building_dir = "/".join(parts[:2])
    elif s.asset == "vehicle":
        s.vehicle_kind = parts[1]
    elif s.asset == "gizmo" and "/".join(parts[:2]) in {item[0] for item in gizmo_dir_items()}:
        s.gizmo_dir = "/".join(parts[:2])
    elif s.asset == "bridge":
        s.theme = parts[1]
        s.bridge_piece = "ramp" if stem.startswith("ramp") else "bridge"
    elif s.asset == "dungeon_tile" and parts[4] in SHAPES:
        s.dungeon_theme, s.tile_kind, s.shape = parts[2], parts[3], parts[4]
    else:
        s.asset = "raw"
        s.raw_path = rel


def _import_gizmo(obj, data, collection):
    variant_rel = obj.mt2.source_variant
    if not variant_rel:
        return
    owner = next(iter(records.parse(data.read(variant_rel))), None)
    if owner is None:
        return
    create_pads(obj, read_pads(owner), collection)
    for member in [obj, *obj.children_recursive]:
        if member.type == "MESH" and member.mt2.role == "NONE":
            member[MESH_HASH_KEY] = mesh_hash(member)
    animations = game_animations(f"{owner.prop('animationFile') or ''}.van")
    if animations:
        import_animations(obj, animations)


def _import_bridge(obj, data, collection):
    rel = variant_path(obj.mt2.theme)
    bridge = read_bridge(data.read(rel)) if data.exists(rel) else None
    if bridge is not None:
        import_bridge_data(obj, bridge, collection)


def _import_creature(obj, data, variant_rel: str, collection):
    creature = read_creature(data.read(variant_rel))
    if creature is None:
        return
    obj.mt2.creature = creature.costume
    obj.mt2.creature_animation = creature.animation
    create_spot(obj, creature.offset or (0.0, 0.0, 0.0), creature.rotation or (0.0, 0.0, 0.0, 1.0), collection)


def _import_pads(obj, data, variant_rel: str, collection):
    if not variant_rel:
        return
    owner = next(iter(records.parse(data.read(variant_rel))), None)
    if owner is not None:
        create_pads(obj, read_pads(owner), collection)


def _import_obstruction(obj, rel: str, data, collection):
    folder, name = rel.rsplit("/", 1) if "/" in rel else ("", rel)
    obs_rel = f"{folder}/{obs_file_name(name)}"
    if data.exists(obs_rel):
        create_obstruction_shape(obj, read_obstruction(data.read(obs_rel).decode("latin-1")), collection)


class MT2_OT_import_file(bpy.types.Operator, ImportHelper):
    bl_idname = "mt2.import_file"
    bl_label = "Import MT2 model"
    bl_description = "Import .vmb files from disk"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".vmb"
    filter_glob: bpy.props.StringProperty(default="*.vmb", options={"HIDDEN"})
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    directory: bpy.props.StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        names = [f.name for f in self.files if f.name] or [Path(self.filepath).name]
        folder = Path(self.directory or Path(self.filepath).parent)
        last = None
        for name in names:
            path = folder / name
            last = import_bytes(context, path.read_bytes(), game_relative(str(path)))
        if last:
            select_only(context, last)

        return {"FINISHED"}


def _game_models(self, context):
    data = game.game_data()
    if data is None:
        return [("", "Set the game folder in the add-on preferences", "")]
    if not _game_items:
        _game_items.extend((rel, rel, "") for rel in data.files("", ".vmb"))

    return _game_items


class MT2_OT_import_game(bpy.types.Operator):
    bl_idname = "mt2.import_game"
    bl_label = "Import from game"
    bl_description = (
        "Search the game's models and import one; the game files are only read. "
        "Shift-click a result to keep the search open and import more"
    )
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "model"

    model: bpy.props.EnumProperty(name="Model", items=_game_models)
    again: bpy.props.BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        if not self.again:
            _search_spot[:] = [event.mouse_x, event.mouse_y]
        context.window_manager.invoke_search_popup(self)

        return {"RUNNING_MODAL"}

    def execute(self, context):
        data = game.game_data()
        if data is None or not self.model:
            self.report({"ERROR"}, "Set the game folder in the add-on preferences first")
            return {"CANCELLED"}
        select_only(context, import_bytes(context, data.read(self.model), self.model))
        if context.window is not None:
            bpy.ops.mt2.keep_searching("INVOKE_DEFAULT")

        return {"FINISHED"}


# The search popup always closes and execute gets no event, so a follow-up invoke reads whether Shift is still held.
class MT2_OT_keep_searching(bpy.types.Operator):
    bl_idname = "mt2.keep_searching"
    bl_label = "Keep searching"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        if event.shift:
            where = {"window": context.window, "area": context.area, "region": context.region}
            bpy.app.timers.register(lambda: _search_again(where), first_interval=0.0)

        return {"FINISHED"}


# The popup opens at the mouse, which is on a result further down by now, so it goes back to where the search opened.
def _search_again(where: dict):
    window = where["window"]
    if window is not None and _search_spot:
        window.cursor_warp(*_search_spot)
    with bpy.context.temp_override(**{k: v for k, v in where.items() if v is not None}):
        bpy.ops.mt2.import_game("INVOKE_DEFAULT", again=True)


class MT2_OT_add_reference(bpy.types.Operator):
    bl_idname = "mt2.add_reference"
    bl_label = "Add reference"
    bl_description = "Add a locked vanilla model at game scale to model next to; it is never exported"
    bl_options = {"REGISTER", "UNDO"}

    model: bpy.props.EnumProperty(name="Model", items=REFERENCES)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        data = game.game_data()
        if data is None:
            self.report({"ERROR"}, "Set the game folder in the add-on preferences first")
            return {"CANCELLED"}
        collection = bpy.data.collections.get("MT2 References") or bpy.data.collections.new("MT2 References")
        if collection.name not in context.scene.collection.children:
            context.scene.collection.children.link(collection)
        obj = to_blender.import_model(
            model.read_model(data.read(self.model)),
            f"Reference {self.model.rsplit('/', 1)[-1][:-4]}",
            game.catalog(),
            collection,
        )
        obj.location = context.scene.cursor.location
        for member in [obj, *obj.children_recursive]:
            member.mt2.role = "REFERENCE"
            member.hide_select = True

        return {"FINISHED"}


_costume_items: list = []


def _game_costumes(self, context):
    data = game.game_data()
    if data is not None and not _costume_items:
        _costume_items.extend(
            (rel, rel.rsplit("/", 1)[-1][: -len(".costume")], rel) for rel in data.files("costumes/", ".costume")
        )

    return _costume_items or [("", "Set the game folder in the add-on preferences", "")]


class MT2_OT_import_costume(bpy.types.Operator):
    bl_idname = "mt2.import_costume"
    bl_label = "Import costume"
    bl_description = (
        "Import a game costume: its skeleton and parts, placed like in the game, with its colors. "
        "Edit or replace parts, then export it as a new costume"
    )
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "costume"

    costume: bpy.props.EnumProperty(name="Costume", items=_game_costumes)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)

        return {"RUNNING_MODAL"}

    def execute(self, context):
        if game.game_data() is None or not self.costume:
            self.report({"ERROR"}, "Set the game folder in the add-on preferences first")
            return {"CANCELLED"}
        select_only(context, import_costume(context, self.costume))

        return {"FINISHED"}


CLASSES = (
    MT2_OT_import_file,
    MT2_OT_import_game,
    MT2_OT_keep_searching,
    MT2_OT_import_costume,
    MT2_OT_add_reference,
)
