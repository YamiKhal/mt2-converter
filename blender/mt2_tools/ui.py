import re
import textwrap

import bpy

from . import game, pipeline
from .anim_objects import REST_POSE, owned_actions
from .convert_out import asset_root
from .costume_objects import costume_root, is_loose_part
from .creature_spot import is_flight_point
from .mt2model.naming import target_problems

LEVEL_ICONS = {"error": "ERROR", "warning": "INFO", "info": "CHECKMARK"}
CHARACTER_WIDTH = 7.5

ASSET_FIELDS = {
    "scenery": ("scenery_type",),
    "tagged": ("tag_place", "tag_kind", "tag_small", "tag_extra"),
    "weapon": ("weapon_category", "item_level"),
    "building": ("building_dir", "display_name"),
    "vehicle": ("vehicle_kind", "display_name", "description"),
    "gizmo": ("gizmo_dir",),
    "modular": ("theme", "slot"),
    "wall": ("theme", "wall_piece"),
    "bridge": ("theme", "bridge_piece"),
    "dungeon_tile": ("dungeon_theme", "tile_kind", "shape"),
    "costume": ("display_name", "rig", "creature_type"),
    "costume_part": ("costume_set", "bone", "normalise"),
    "raw": ("raw_path",),
}
NAMELESS = ("raw", "costume_part", "dungeon_tile", "wall", "bridge")
ANIMATED = ("gizmo", "costume")
LIGHT_ASSETS = ("scenery", "tagged")
PAD_ASSETS = ("building", "vehicle", "gizmo")

_vanilla_categories: dict[str, bool] = {}


class _Panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MT2"


def _split(layout):
    layout.use_property_split = True
    layout.use_property_decorate = False

    return layout


class MT2_PT_import(_Panel):
    bl_label = "Import"

    def draw(self, context):
        layout = self.layout
        if not game.preferences().game_path or game.game_data() is None:
            layout.operator("mt2.setup", icon="ERROR")
            return
        column = layout.column()
        column.scale_y = 1.2
        column.operator("mt2.import_game", icon="VIEWZOOM")
        row = layout.row(align=True)
        row.operator("mt2.import_file", text="File", icon="FILEBROWSER")
        row.operator("mt2.import_costume", text="Costume", icon="ARMATURE_DATA")
        row.operator("mt2.add_reference", text="Reference", icon="OUTLINER_OB_EMPTY")
        row = layout.row(align=True)
        row.operator("mt2.convert", icon="MODIFIER")
        row.operator("mt2.new_theme", icon="ASSET_MANAGER")


class MT2_PT_asset(_Panel):
    bl_label = "Asset"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mt2
        root = asset_root(context.active_object)
        if not settings.mod_id or game.project_dir() is None:
            layout.operator("mt2.setup", icon="ERROR")
        if root is None or is_loose_part(context.active_object):
            layout.operator("mt2.make_asset", icon="ADD")
            return
        _split(layout)
        s = root.mt2
        layout.prop(s, "asset")
        if s.asset not in NAMELESS:
            layout.prop(s, "name")
        for field in _fields(root):
            layout.prop(s, field)
        problems = target_problems(pipeline.target_for(root))
        for line in _wrap(context, problems[0], 30) if problems else []:
            layout.label(text=line, icon="ERROR")
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("mt2.check", icon="CHECKMARK")
        row.operator("mt2.export", icon="EXPORT")
        if s.exported_path:
            row.operator("mt2.forget_export", text="", icon="LOCKED")
        _draw_findings(layout, context, root)


def _fields(root) -> list[str]:
    s = root.mt2
    fields = list(ASSET_FIELDS.get(s.asset, ()))
    if s.asset == "costume_part" and costume_root(root.parent) is not None:
        fields = ["normalise"]
    if s.asset == "weapon" and not _is_vanilla_category(s.weapon_category):
        fields.append("display_name")
    if is_flight_point(root):
        fields += ["creature", "creature_animation"]

    return fields


def _is_vanilla_category(category: str) -> bool:
    if category not in _vanilla_categories:
        data = game.game_data()
        names = data.sources[-1].names() if data else []
        _vanilla_categories[category] = any(n.startswith(f"weapons/{category}/") for n in names)

    return _vanilla_categories[category]


def _draw_findings(layout, context, root):
    settings = context.scene.mt2
    if settings.findings_root != root:
        return
    notes = [f for f in settings.findings if f.level == "info"]
    for index, finding in enumerate(settings.findings):
        if finding.level != "info" or settings.show_notes:
            _draw_finding(layout.box(), context, index, finding)
    if notes:
        text = f"{len(notes)} note{'s' if len(notes) > 1 else ''}"
        icon = "DISCLOSURE_TRI_DOWN" if settings.show_notes else "DISCLOSURE_TRI_RIGHT"
        layout.prop(settings, "show_notes", text=text, icon=icon, emboss=False)


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


class MT2_PT_costume_colors(_Panel):
    bl_label = "Colors"
    bl_parent_id = "MT2_PT_asset"

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and root.mt2.asset == "costume"

    def draw(self, context):
        root = asset_root(context.active_object)
        grid = self.layout.grid_flow(columns=4, even_columns=True, align=True)
        for entry in root.mt2.palette:
            grid.prop(entry, "color", text="")


class MT2_PT_animation(_Panel):
    bl_label = "Animation"
    bl_parent_id = "MT2_PT_asset"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and root.mt2.asset in ANIMATED

    def draw(self, context):
        layout = self.layout
        root = asset_root(context.active_object)
        has_actions = bool(owned_actions(root))
        row = layout.row(align=True)
        if has_actions:
            row.prop(root.mt2, "animation", text="")
        row.operator("mt2.new_animation", text="" if has_actions else "New animation", icon="ADD")
        if root.mt2.asset == "costume":
            row.operator("mt2.import_animations", text="", icon="IMPORT")
        if has_actions and root.mt2.animation != REST_POSE:
            layout.prop(root.mt2, "playback", text="")


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


class MT2_PT_materials(_Panel):
    bl_label = "Materials"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def draw(self, context):
        layout = self.layout
        names = context.window_manager.mt2_materials
        column = layout.column(align=True)
        for index, slot in enumerate(context.active_object.material_slots):
            game_name = _game_name(slot.material)
            missing = bool(game_name) and game_name not in names
            column.operator("mt2.pick_game_material", text=game_name or "Empty",
                            icon="ERROR" if missing else "MATERIAL").slot = index
        row = layout.row(align=True)
        for name in ("Material_tint", "emissive", "costume"):
            row.operator("mt2.setup_material", text=name.replace("_tint", "")).name = name
        row.operator("mt2.new_textured_material", text="", icon="TEXTURE")


def _game_name(material) -> str:
    if material is None:
        return ""

    return material.mt2.game_name or re.sub(r"\.\d{3}$", "", material.name)


class MT2_PT_helpers(_Panel):
    bl_label = "Helpers"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        root = asset_root(obj)
        asset = root.mt2.asset if root else ""
        column = layout.column(align=True)
        column.operator("mt2.bake_colors", icon="RENDER_STILL")
        column.operator("mt2.flat_colors", icon="MOD_TRIANGULATE")
        column = layout.column(align=True)
        if asset in LIGHT_ASSETS:
            column.operator("mt2.add_light", icon="LIGHT_POINT")
            column.operator("mt2.add_obstruction", icon="MOD_BOOLEAN")
        if asset in PAD_ASSETS:
            row = column.row(align=True)
            row.operator("mt2.add_pad", icon="MESH_PLANE")
            row.operator("mt2.add_entrance", icon="CURVE_PATH")
        if asset == "dungeon_tile":
            column.operator("mt2.add_socket", icon="EMPTY_SINGLE_ARROW")
        if costume_root(obj) is not None and asset != "costume_part":
            row = column.row(align=True)
            row.operator("mt2.add_bone", icon="BONE_DATA")
            row.operator("mt2.set_rest_pose", icon="ARMATURE_DATA")
        if root is not None and is_flight_point(root):
            column.operator("mt2.add_creature_spot", icon="EMPTY_ARROWS")
        if asset in ("scenery", "building"):
            column.operator("mt2.footprint_preview", icon="SNAP_FACE")
        if obj is not None and obj is not root and obj.mt2.role != "NONE":
            _split(layout).prop(obj.mt2, "role")
        if obj is not None and obj.mt2.role == "SOCKET":
            _split(layout).prop(obj.mt2, "socket_tags")
        if asset in ("modular", "wall", "bridge"):
            layout.prop(context.scene.mt2, "show_guides")


class MT2_PT_project(_Panel):
    bl_label = "Mod"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = _split(self.layout)
        settings = context.scene.mt2
        layout.prop(settings, "project_dir")
        row = layout.row(align=True)
        row.prop(settings, "mod_id")
        row.operator("mt2.load_project", text="", icon="FILE_REFRESH")
        folder = game.project_dir()
        if folder is not None and not (folder / "manifest.json").exists():
            layout.operator("mt2.create_project", icon="ADD")


class MT2_PT_art_pack(_Panel):
    bl_label = "Art pack"
    bl_parent_id = "MT2_PT_project"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mt2, "art_pack", text="")

    def draw(self, context):
        layout = _split(self.layout)
        settings = context.scene.mt2
        layout.active = settings.art_pack
        layout.prop(settings, "art_pack_name")
        layout.prop(settings, "art_pack_description")
        layout.prop(settings, "art_pack_cost")
        layout.prop(settings, "art_pack_costumes")
        layout.prop(settings, "art_pack_exotic")


class MT2_PT_weapon_packs(_Panel):
    bl_label = "Weapon packs"
    bl_parent_id = "MT2_PT_project"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.mt2, "weapon_packs", text="")

    def draw(self, context):
        layout = _split(self.layout)
        layout.active = context.scene.mt2.weapon_packs
        layout.prop(context.scene.mt2, "weapon_pack_cost")


CLASSES = (MT2_PT_import, MT2_PT_asset, MT2_PT_costume_colors, MT2_PT_animation, MT2_PT_paint, MT2_PT_palette,
           MT2_PT_materials, MT2_PT_helpers, MT2_PT_project, MT2_PT_art_pack, MT2_PT_weapon_packs)
