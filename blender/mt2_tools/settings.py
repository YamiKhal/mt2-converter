import bpy

from . import game
from .mt2model.assets import ASSET_TYPES, MODULAR_SLOTS, PLACEABLE_SCENERY_TYPES, TAG_KINDS, TAG_PLACES
from .mt2model.variants import building_kinds

ROLES = (
    ("NONE", "Model", "Exported as part of the model"),
    ("LIGHT", "Point light", "Becomes a 'light' fragment: a point light at its centre, radius from its size"),
    ("OBSTRUCTION", "Obstruction shape", "Its faces become the footprint polygons in <name>_obs.vrt"),
    ("COLLISION", "Collision", "Dungeon tiles only: the physics mesh"),
    ("NAVMESH", "Navmesh", "Dungeon tiles only: the walkable surface"),
    ("REFERENCE", "Reference", "A vanilla model for scale; never exported"),
    ("PREVIEW", "Preview", "A helper drawn by the add-on; never exported"),
)


def _items(values) -> list[tuple[str, str, str]]:
    return [(v, v.replace("_", " ").capitalize(), "") for v in values]


_building_items: list = []
_building_source: list = [None]


def building_dir_items(self=None, context=None):
    data = game.game_data()
    if _building_source[0] is data and _building_items:
        return _building_items
    _building_source[0] = data
    _building_items.clear()
    if data is not None:
        for kind in building_kinds(data):
            if kind.directory.startswith("buildings/"):
                _building_items.append((kind.directory, kind.name, f"{kind.directory} (key {kind.key})"))
    if not _building_items:
        _building_items.append(("buildings/tavern", "Tavern", "buildings/tavern"))

    return _building_items


def _forget_findings(self, context):
    scene = context.scene if context else None
    if scene is not None and scene.mt2.findings_root == self.id_data:
        scene.mt2.findings.clear()


class MT2_Finding(bpy.types.PropertyGroup):
    level: bpy.props.StringProperty()
    message: bpy.props.StringProperty()
    object_name: bpy.props.StringProperty()


class MT2_MaterialName(bpy.types.PropertyGroup):
    pass


class MT2_RecentColor(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR_GAMMA", size=4, min=0.0, max=1.0)


class MT2_SceneSettings(bpy.types.PropertyGroup):
    project_dir: bpy.props.StringProperty(
        name="Mod folder",
        description="The mod's source folder (the one with manifest.json); exports go here",
        subtype="DIR_PATH",
    )
    mod_id: bpy.props.StringProperty(
        name="Mod id",
        description="The manifest id; prefixes every exported file name so it can't collide with vanilla or other mods",
    )
    paint_color: bpy.props.FloatVectorProperty(
        name="Color", subtype="COLOR_GAMMA", size=4, min=0.0, max=1.0, default=(0.8, 0.8, 0.8, 1.0),
    )
    recent_colors: bpy.props.CollectionProperty(type=MT2_RecentColor)
    select_connected: bpy.props.BoolProperty(
        name="Connected only", default=True,
        description="Only select faces touching the selection through faces of the same color",
    )
    palette_slot: bpy.props.IntProperty(name="Slot", min=1, max=8, default=1)
    shade: bpy.props.FloatProperty(
        name="Shade", description="0 keeps the slot color, 1 halves its brightness", min=0.0, max=1.0, default=0.4,
    )
    shade_top: bpy.props.FloatProperty(name="Top", min=0.0, max=1.0, default=0.3)
    shade_bottom: bpy.props.FloatProperty(name="Bottom", min=0.0, max=1.0, default=0.55)
    findings: bpy.props.CollectionProperty(type=MT2_Finding)
    findings_root: bpy.props.PointerProperty(type=bpy.types.Object, description="The asset the findings belong to")


class MT2_ObjectSettings(bpy.types.PropertyGroup):
    is_asset: bpy.props.BoolProperty(name="Asset root")
    asset: bpy.props.EnumProperty(
        name="Asset type",
        items=[(t.key, t.label, t.description) for t in ASSET_TYPES.values()],
        default="scenery", update=_forget_findings,
    )
    name: bpy.props.StringProperty(name="File name", description="Becomes <mod id>_<name>.vmb", update=_forget_findings)
    scenery_type: bpy.props.EnumProperty(
        name="Scenery type", items=_items(PLACEABLE_SCENERY_TYPES), default="stone", update=_forget_findings,
    )
    tag_place: bpy.props.EnumProperty(name="Place", items=_items(TAG_PLACES), default="floor", update=_forget_findings)
    tag_kind: bpy.props.EnumProperty(name="Kind", items=_items(TAG_KINDS), default="prop", update=_forget_findings)
    tag_small: bpy.props.BoolProperty(name="Small", description="Fits sockets tagged 'small'", update=_forget_findings)
    tag_extra: bpy.props.StringProperty(
        name="Extra tags", description="Space-separated, e.g. a theme: cave mansion", update=_forget_findings,
    )
    weapon_category: bpy.props.StringProperty(name="Category", default="swords", update=_forget_findings)
    item_level: bpy.props.IntProperty(name="Item level", min=0, max=999, default=15, update=_forget_findings)
    costume_set: bpy.props.StringProperty(
        name="Costume folder", description="costumes/<folder>/<bone>.vmb", update=_forget_findings,
    )
    bone: bpy.props.StringProperty(name="Bone", default="head", update=_forget_findings)
    normalise: bpy.props.BoolProperty(
        name="Normalise size", default=True,
        description="Scale the part so its largest side is 1, like vanilla parts; the scale to use as modelScale is reported",
        update=_forget_findings,
    )
    model_scale: bpy.props.FloatProperty(name="modelScale", description="Set by the last export", default=1.0)
    theme: bpy.props.StringProperty(name="Theme", update=_forget_findings)
    slot: bpy.props.EnumProperty(name="Piece", items=_items(MODULAR_SLOTS), default="sides", update=_forget_findings)
    wall_piece: bpy.props.EnumProperty(
        name="Piece", items=_items(("wall", "turret")), default="wall", update=_forget_findings,
    )
    building_dir: bpy.props.EnumProperty(name="Building type", items=building_dir_items, update=_forget_findings)
    display_name: bpy.props.StringProperty(
        name="Display name", update=_forget_findings,
        description="Shown in game: the name of a building variant, or of a new weapon category",
    )
    raw_path: bpy.props.StringProperty(
        name="Game path", description="Relative path, e.g. scenery/stone/my_rock.vmb", update=_forget_findings,
    )
    role: bpy.props.EnumProperty(name="Role", items=ROLES, default="NONE")
    source_path: bpy.props.StringProperty(name="Imported from")
    source_variant: bpy.props.StringProperty(name="Variant template")
    exported_path: bpy.props.StringProperty(name="Exported as")


class MT2_MaterialSettings(bpy.types.PropertyGroup):
    game_name: bpy.props.StringProperty(
        name="Game material", description="The materials/<name>.mat this slot exports as",
    )


CLASSES = (MT2_Finding, MT2_MaterialName, MT2_RecentColor, MT2_SceneSettings, MT2_ObjectSettings, MT2_MaterialSettings)


def register_properties():
    bpy.types.Scene.mt2 = bpy.props.PointerProperty(type=MT2_SceneSettings)
    bpy.types.Object.mt2 = bpy.props.PointerProperty(type=MT2_ObjectSettings)
    bpy.types.Material.mt2 = bpy.props.PointerProperty(type=MT2_MaterialSettings)
    bpy.types.WindowManager.mt2_materials = bpy.props.CollectionProperty(type=MT2_MaterialName)


def unregister_properties():
    del bpy.types.WindowManager.mt2_materials
    del bpy.types.Material.mt2
    del bpy.types.Object.mt2
    del bpy.types.Scene.mt2
