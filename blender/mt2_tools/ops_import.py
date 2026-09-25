from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from . import convert_in, game
from .mt2model import model
from .mt2model.assets import guess_from_path
from .mt2model.axes import swap_ground
from .mt2model.obstruction import obs_file_name, read_obstruction
from .mt2model.variants import variant_for_model
from .settings import building_dir_items

TOP_FOLDERS = ("scenery", "weapons", "costumes", "building_themes", "wall_themes", "buildings", "bridge_themes",
               "vehicles", "gizmo", "dungeon", "portals", "depots", "docks", "skeletons")

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
    obj = convert_in.import_model(model.read_model(raw), stem, game.catalog(), collection)
    _describe(obj, rel, stem)
    if data is not None:
        _import_obstruction(obj, rel, data, collection)
        if obj.mt2.asset == "building":
            obj.mt2.source_variant = variant_for_model(data, rel) or ""

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
    else:
        s.raw_path = rel


def _import_obstruction(obj, rel: str, data, collection):
    folder, name = rel.rsplit("/", 1) if "/" in rel else ("", rel)
    obs_rel = f"{folder}/{obs_file_name(name)}"
    if not data.exists(obs_rel):
        return
    polygons = read_obstruction(data.read(obs_rel).decode("latin-1"))
    vertices, faces = [], []
    for polygon in polygons:
        faces.append(tuple(range(len(vertices), len(vertices) + len(polygon))))
        vertices += [(*swap_ground(point), 0.0) for point in reversed(polygon)]
    mesh = bpy.data.meshes.new(f"{obj.name} obstruction")
    mesh.from_pydata(vertices, [], faces)
    shape = bpy.data.objects.new(f"{obj.name} obstruction", mesh)
    collection.objects.link(shape)
    shape.parent = obj
    shape.mt2.role = "OBSTRUCTION"
    shape.display_type = "WIRE"
    shape.hide_render = True


def _select(context, obj):
    for other in context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


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
            _select(context, last)

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
    bl_description = "Search the game's models and import one; the game files are only read"
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "model"

    model: bpy.props.EnumProperty(name="Model", items=_game_models)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)

        return {"RUNNING_MODAL"}

    def execute(self, context):
        data = game.game_data()
        if data is None or not self.model:
            self.report({"ERROR"}, "Set the game folder in the add-on preferences first")
            return {"CANCELLED"}
        _select(context, import_bytes(context, data.read(self.model), self.model))

        return {"FINISHED"}


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
        obj = convert_in.import_model(model.read_model(data.read(self.model)), f"Reference {self.model.rsplit('/', 1)[-1][:-4]}",
                                      game.catalog(), collection)
        obj.location = context.scene.cursor.location
        for member in [obj, *obj.children_recursive]:
            member.mt2.role = "REFERENCE"
            member.hide_select = True

        return {"FINISHED"}


CLASSES = (MT2_OT_import_file, MT2_OT_import_game, MT2_OT_add_reference)
