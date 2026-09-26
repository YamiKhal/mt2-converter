import bpy

from . import game
from .mt2model.naming import clean_word, dungeon_theme_name, prefixed
from .mt2model.themes import FAMILIES, copy_theme, read_colors, theme_names

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
    bl_description = ("Copy a game theme (dungeon, modular building, wall or bridge) into the mod under a new name. "
                      "Then import its pieces from the mod folder and change them")
    bl_options = {"REGISTER", "UNDO"}

    family: bpy.props.EnumProperty(
        name="Kind", items=[(f.key, f.label, "") for f in FAMILIES.values()], default="dungeon",
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
        self.report({"INFO"}, f"Wrote {FAMILIES[self.family].folder}/{name} ({len(files)} files). "
                              f"Import its pieces to change them")

        return {"FINISHED"}


CLASSES = (MT2_OT_new_theme,)
