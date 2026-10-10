import shutil

import bpy

from .. import game
from ..conversion.to_game import asset_root
from ..export.pipeline import target_for, write_art_pack
from ..mt2model.naming import clean_word, dungeon_theme_name, model_path, prefixed
from ..mt2model.themes import ASSET_FAMILIES, FAMILIES, copy_theme, read_colors, theme_files, theme_names
from ..objects.selection import select_only
from ..objects.themes import theme_field, themes_in_mod
from .importing import import_bytes

_source_items: list = []


def _sources(self, context):
    data = game.game_data()
    _source_items.clear()
    if data is not None:
        _source_items.extend((t, t.replace("_", " ").capitalize(), "") for t in theme_names(data, self.family))

    return _source_items or [("", "Set the game folder first", "")]


def _source_changed(self, context):
    data = game.game_data()
    conf = f"dungeon/themes/{self.source}/theme.conf"
    if self.family != "dungeon" or data is None or not self.source or not data.exists(conf):
        return
    for index, color in enumerate(read_colors(data.read(conf))):
        setattr(self, f"color_{index + 1}", color)


class MT2_OT_new_theme(bpy.types.Operator):
    bl_idname = "mt2.new_theme"
    bl_label = "New theme"
    bl_description = (
        "Copy a game theme (dungeon, modular building, wall or bridge) into the mod under a new name. "
        "Its pieces are then listed under Themes"
    )
    bl_options = {"REGISTER", "UNDO"}

    family: bpy.props.EnumProperty(
        name="Kind",
        items=[(f.key, f.label, "") for f in FAMILIES.values()],
        default="dungeon",
        update=_source_changed,
    )
    source: bpy.props.EnumProperty(name="Start from", items=_sources, update=_source_changed)
    name: bpy.props.StringProperty(name="Name", default="crypt")
    color_1: bpy.props.FloatVectorProperty(name="Color 1", subtype="COLOR_GAMMA", size=4, min=0, max=1)
    color_2: bpy.props.FloatVectorProperty(name="Color 2", subtype="COLOR_GAMMA", size=4, min=0, max=1)
    color_3: bpy.props.FloatVectorProperty(name="Color 3", subtype="COLOR_GAMMA", size=4, min=0, max=1)
    color_4: bpy.props.FloatVectorProperty(name="Color 4", subtype="COLOR_GAMMA", size=4, min=0, max=1)

    def invoke(self, context, event):
        _source_changed(self, context)

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "family")
        layout.prop(self, "source")
        layout.prop(self, "name")
        if self.family == "dungeon":
            row = layout.row(align=True)
            for index in range(1, 5):
                row.prop(self, f"color_{index}", text="")

    def execute(self, context):
        folder = game.project_dir()
        mod_id = context.scene.mt2.mod_id
        data = game.game_data()
        if folder is None or not mod_id or data is None or not self.source:
            self.report({"ERROR"}, "Set the game folder, the mod folder and the mod id first")
            return {"CANCELLED"}
        word = clean_word(self.name) or "theme"
        name = dungeon_theme_name(mod_id, word) if self.family == "dungeon" else prefixed(mod_id, word)
        target = folder / FAMILIES[self.family].folder / name
        if target.exists():
            self.report({"ERROR"}, f"The mod already has a theme called {name}")
            return {"CANCELLED"}
        colors = [tuple(getattr(self, f"color_{i}")) for i in range(1, 5)] if self.family == "dungeon" else None
        files = copy_theme(data, self.family, self.source, name, colors)
        for rel, content in files.items():
            path = folder / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        game.forget()
        context.scene.mt2.open_theme = f"{FAMILIES[self.family].folder}/{name}"
        redraw_sidebars(context)
        self.report({"INFO"}, f"Wrote {FAMILIES[self.family].folder}/{name}. Pick its pieces under Themes")

        return {"FINISHED"}


# The Themes panel shows and hides with the mod's themes, and Blender won't redraw the sidebar for that by itself.
def redraw_sidebars(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def pieces_in_scene(scene: bpy.types.Scene) -> dict[str, bpy.types.Object]:
    found = {}
    for obj in scene.objects:
        if obj.mt2.is_asset and obj.mt2.asset in ASSET_FAMILIES:
            found.setdefault(model_path(target_for(obj)), obj)

    return found


class MT2_OT_open_theme(bpy.types.Operator):
    bl_idname = "mt2.open_theme"
    bl_label = "Show pieces"
    bl_description = "Show or hide this theme's pieces"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()

    def execute(self, context):
        settings = context.scene.mt2
        settings.open_theme = "" if settings.open_theme == self.key else self.key

        return {"FINISHED"}


class MT2_OT_import_theme_piece(bpy.types.Operator):
    bl_idname = "mt2.import_theme_piece"
    bl_label = "Import piece"
    bl_description = "Import this piece of the theme, or select it when it's already in the scene"
    bl_options = {"REGISTER", "UNDO"}

    rel: bpy.props.StringProperty()

    def execute(self, context):
        existing = pieces_in_scene(context.scene).get(self.rel)
        if existing is not None:
            select_only(context, existing)
            return {"FINISHED"}
        data = game.game_data()
        if data is None or not data.exists(self.rel):
            self.report({"ERROR"}, f"{self.rel} isn't in the mod folder anymore")
            return {"CANCELLED"}
        select_only(context, import_bytes(context, data.read(self.rel), self.rel))

        return {"FINISHED"}


_theme_items: list = []


def _themes_for_asset(self, context):
    _theme_items.clear()
    root = asset_root(context.active_object)
    data = game.game_data()
    family = ASSET_FAMILIES.get(root.mt2.asset) if root else None
    if family is None or data is None:
        return [("", "No themes", "")]
    own = [t.name for t in themes_in_mod(data) if t.family == family]
    _theme_items.extend((name, name, "In this mod") for name in own)
    others = [name for name in theme_names(data, family) if name not in own]
    if own and others:
        _theme_items.append(None)
    _theme_items.extend((name, name, "The game's") for name in others)

    return _theme_items or [("", "No themes", "")]


class MT2_OT_pick_theme(bpy.types.Operator):
    bl_idname = "mt2.pick_theme"
    bl_label = "Theme"
    bl_description = "The theme this model belongs to. Pieces picked under Themes already know theirs"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    bl_property = "theme"

    theme: bpy.props.EnumProperty(name="Theme", items=_themes_for_asset)

    def execute(self, context):
        root = asset_root(context.active_object)
        if root is None or not self.theme:
            return {"CANCELLED"}
        setattr(root.mt2, theme_field(root.mt2.asset), self.theme)

        return {"FINISHED"}


class MT2_OT_delete_theme(bpy.types.Operator):
    bl_idname = "mt2.delete_theme"
    bl_label = "Delete theme"
    bl_description = "Delete this theme's files from the mod folder. Models in the scene stay"
    bl_options = {"REGISTER", "INTERNAL"}

    key: bpy.props.StringProperty()

    def invoke(self, context, event):
        name = self.key.rsplit("/", 1)[-1]
        count = len(self._files())
        message = f"Delete the theme '{name}' and its {count} files from the mod folder? This can't be undone"

        return context.window_manager.invoke_confirm(self, event, message=message)

    def execute(self, context):
        folder = game.project_dir()
        files = self._files()
        if folder is None or not files:
            self.report({"ERROR"}, "The theme isn't in the mod folder")
            return {"CANCELLED"}
        for rel in files:
            (folder / rel).unlink(missing_ok=True)
        shutil.rmtree(folder / self.key, ignore_errors=True)
        game.rescan()
        if context.scene.mt2.open_theme == self.key:
            context.scene.mt2.open_theme = ""
        write_art_pack(folder)
        redraw_sidebars(context)
        self.report({"INFO"}, f"Deleted {self.key} ({len(files)} files)")

        return {"FINISHED"}

    def _files(self) -> list[str]:
        data = game.game_data()
        theme = next((t for t in themes_in_mod(data) if t.key == self.key), None)
        if theme is None:
            return []

        return theme_files(data.overlay_names(), theme.family, theme.name)


def draw_theme_context_menu(self, context):
    button = getattr(context, "button_operator", None)
    if button is None or button.bl_rna.identifier != MT2_OT_open_theme.__name__:
        return
    self.layout.separator()
    self.layout.operator("mt2.delete_theme", icon="TRASH").key = button.key


CLASSES = (MT2_OT_new_theme, MT2_OT_open_theme, MT2_OT_import_theme_piece, MT2_OT_pick_theme, MT2_OT_delete_theme)
