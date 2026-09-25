import re
import textwrap

import bpy

from . import game, pipeline
from .convert_out import asset_root
from .mt2model.naming import model_path, target_problems

LEVEL_ICONS = {"error": "ERROR", "warning": "INFO", "info": "CHECKMARK"}
CHARACTER_WIDTH = 7.5

ASSET_FIELDS = {
    "scenery": ("scenery_type",),
    "tagged": ("tag_place", "tag_kind", "tag_small", "tag_extra"),
    "weapon": ("weapon_category", "item_level", "display_name"),
    "building": ("building_dir", "display_name", "source_variant"),
    "modular": ("theme", "slot"),
    "wall": ("theme", "wall_piece"),
    "costume_part": ("costume_set", "bone", "normalise"),
    "raw": ("raw_path",),
}


class _Panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MT2"


class MT2_PT_project(_Panel):
    bl_label = "Mod"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mt2
        if not game.preferences().game_path:
            box = layout.box()
            box.label(text="Game folder not set", icon="ERROR")
            box.operator("mt2.detect_paths", icon="VIEWZOOM")
        elif game.game_data() is None:
            layout.label(text="Game data not found in the game folder", icon="ERROR")
        layout.prop(settings, "project_dir")
        row = layout.row(align=True)
        row.prop(settings, "mod_id")
        row.operator("mt2.load_project", text="", icon="FILE_REFRESH")
        folder = game.project_dir()
        if folder is not None and not (folder / "manifest.json").exists():
            layout.operator("mt2.create_project", icon="ADD")


class MT2_PT_import(_Panel):
    bl_label = "Import"

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("mt2.import_game", icon="VIEWZOOM")
        col.operator("mt2.import_file", icon="FILEBROWSER")
        col.operator("mt2.add_reference", icon="OUTLINER_OB_EMPTY")


class MT2_PT_asset(_Panel):
    bl_label = "Asset"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        root = asset_root(obj)
        if obj is not None and obj.mt2.role != "NONE":
            layout.label(text=f"Role: {obj.mt2.bl_rna.properties['role'].enum_items[obj.mt2.role].name}", icon="INFO")
        if root is None:
            layout.operator("mt2.make_asset", icon="ADD")
            return
        s = root.mt2
        layout.label(text=root.name, icon="OBJECT_DATA")
        layout.prop(s, "asset")
        if s.asset != "raw":
            layout.prop(s, "name")
        for field in ASSET_FIELDS.get(s.asset, ()):
            layout.prop(s, field)
        if s.asset == "costume_part" and s.model_scale != 1.0:
            layout.label(text=f"modelScale {s.model_scale:.6f}")
        target = pipeline.target_for(root)
        problems = target_problems(target)
        layout.label(text=problems[0] if problems else model_path(target), icon="ERROR" if problems else "FILE")
        if s.exported_path:
            row = layout.row()
            row.label(text=f"Exported as {s.exported_path}", icon="LOCKED")
            row.operator("mt2.forget_export", text="", icon="UNLOCKED")
        row = layout.row(align=True)
        row.operator("mt2.check", icon="CHECKMARK")
        row.operator("mt2.export", icon="EXPORT")
        settings = context.scene.mt2
        if settings.findings_root == root:
            for index, finding in enumerate(settings.findings):
                _draw_finding(layout.box(), context, index, finding)


def _draw_finding(layout, context, index: int, finding):
    row = layout.row()
    text = row.column(align=True)
    icon = LEVEL_ICONS.get(finding.level, "DOT")
    for line in _wrap(context, finding.message, margin=60 if finding.object_name else 30):
        text.label(text=line, icon=icon)
        icon = "BLANK1"
    if finding.object_name:
        row.operator("mt2.select_finding", text="", icon="RESTRICT_SELECT_OFF").index = index


def _wrap(context, text: str, margin: int) -> list[str]:
    region = getattr(context, "region", None)
    width = (region.width if region else 300) - margin
    scale = context.preferences.system.ui_scale or 1.0
    columns = max(16, int(width / (CHARACTER_WIDTH * scale)))

    return textwrap.wrap(text, columns) or [""]


class MT2_PT_materials(_Panel):
    bl_label = "Materials"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        names = context.window_manager.mt2_materials
        for index, slot in enumerate(obj.material_slots):
            row = layout.row(align=True)
            row.label(text=f"Slot {index + 1}")
            game_name = _game_name(slot.material)
            missing = bool(game_name) and game_name not in names
            button = row.operator("mt2.pick_game_material", text=game_name or "Empty",
                                  icon="ERROR" if missing else "MATERIAL")
            button.slot = index
        row = layout.row(align=True)
        for name in ("Material_tint", "emissive", "costume"):
            row.operator("mt2.setup_material", text=name.replace("_tint", "")).name = name
        layout.operator("mt2.new_textured_material", icon="TEXTURE")


def _game_name(material) -> str:
    if material is None:
        return ""

    return material.mt2.game_name or re.sub(r"\.\d{3}$", "", material.name)


class MT2_PT_paint(_Panel):
    bl_label = "Paint"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mt2
        row = layout.row()
        paint = row.row(align=True)
        paint.prop(settings, "paint_color", text="")
        paint.operator("mt2.fill_color", icon="BRUSH_DATA")
        row.operator("mt2.pick_color", text="", icon="EYEDROPPER")
        row = layout.row(align=True)
        row.operator("mt2.select_color", icon="RESTRICT_SELECT_OFF")
        row.prop(settings, "select_connected", text="", icon="LINKED")
        if settings.recent_colors:
            layout.label(text="Recent colors")
            grid = layout.grid_flow(columns=4, even_columns=True, align=True)
            for index, entry in enumerate(settings.recent_colors):
                cell = grid.row(align=True)
                cell.prop(entry, "color", text="")
                cell.operator("mt2.use_color", text="", icon="FORWARD").index = index


class MT2_PT_palette(_Panel):
    bl_label = "Palette slots"
    bl_parent_id = "MT2_PT_paint"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mt2
        layout.label(text="Costume parts use 1-8, dungeon tiles 1-4")
        grid = layout.grid_flow(columns=4, align=True)
        for slot in range(1, 9):
            grid.operator("mt2.palette_slot", text=str(slot), depress=settings.palette_slot == slot).slot = slot
        row = layout.row(align=True)
        row.prop(settings, "shade")
        row.operator("mt2.shade").gradient = False
        row = layout.row(align=True)
        row.prop(settings, "shade_top")
        row.prop(settings, "shade_bottom")
        row.operator("mt2.shade", text="Gradient").gradient = True
        layout.operator("mt2.palette_preview", icon="COLOR")


class MT2_PT_helpers(_Panel):
    bl_label = "Helpers"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("mt2.bake_colors", icon="RENDER_STILL")
        col.operator("mt2.flat_colors", icon="MOD_TRIANGULATE")
        col.separator()
        col.operator("mt2.add_light", icon="LIGHT_POINT")
        col.operator("mt2.add_obstruction", icon="MOD_BOOLEAN")
        col.operator("mt2.footprint_preview", icon="SNAP_FACE")
        obj = context.active_object
        if obj is not None:
            self.layout.prop(obj.mt2, "role")


CLASSES = (MT2_PT_project, MT2_PT_import, MT2_PT_asset, MT2_PT_materials, MT2_PT_paint, MT2_PT_palette, MT2_PT_helpers)
