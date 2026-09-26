import bpy

from . import game
from .anim_objects import NAME_KEY, PLAYBACK_KEY, assign, owned_actions
from .mt2model.animations import PLAYBACK_TYPES
from .mt2model.dungeons import SHAPES
from .mt2model.assets import ASSET_TYPES, MODULAR_SLOTS, PLACEABLE_SCENERY_TYPES, TAG_KINDS, TAG_PLACES
from .mt2model.variants import building_kinds, gizmo_dirs
from .palette import show_palette

ROLES = (
    ("NONE", "Model", "Exported as part of the model"),
    ("LIGHT", "Point light", "Becomes a 'light' fragment: a point light at its centre, radius from its size"),
    ("OBSTRUCTION", "Obstruction shape", "Its faces become the footprint polygons in <name>_obs.vrt"),
    ("COLLISION", "Collision", "Dungeon tiles only: the physics mesh"),
    ("NAVMESH", "Navmesh", "Dungeon tiles only: the walkable surface"),
    ("PAD", "NPC pad", "A flat 4-corner area where NPCs stand; its entrance lines are its children"),
    ("ENTRANCE", "Entrance", "A line NPCs walk along, from outside the building to its pad"),
    ("SOCKET", "Prop socket", "Dungeon tiles: a spot where the dungeon places a prop whose tags match"),
    ("BONE", "Bone", "A skeleton bone of a costume; parts parented to it follow it"),
    ("REFERENCE", "Reference", "A vanilla model for scale; never exported"),
    ("PREVIEW", "Preview", "A helper drawn by the add-on; never exported"),
)


def _items(values) -> list[tuple[str, str, str]]:
    return [(v, v.replace("_", " ").capitalize(), "") for v in values]


_building_items: list = []
_building_source: list = [None]


_gizmo_items: list = []
_animation_items: list = []


def gizmo_dir_items(self=None, context=None):
    data = game.game_data()
    if not _gizmo_items:
        dirs = gizmo_dirs(data) if data is not None else []
        _gizmo_items.extend((d, d.rsplit("/", 1)[-1].capitalize(), d) for d in dirs)

    return _gizmo_items or [("gizmo/container", "Container", "gizmo/container")]


def animation_items(self, context):
    _animation_items.clear()
    owner = self.id_data
    _animation_items.extend((a.name, a.get(NAME_KEY, a.name), "") for a in owned_actions(owner))

    return _animation_items or [("", "No animations", "")]


def _animation_changed(self, context):
    action = bpy.data.actions.get(self.animation)
    if action is not None:
        assign(self.id_data, action)
        self.playback = action.get(PLAYBACK_KEY, "Once")


def _playback_changed(self, context):
    action = bpy.data.actions.get(self.animation)
    if action is not None:
        action[PLAYBACK_KEY] = self.playback


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


def _art_pack_changed(self, context):
    from . import pipeline

    pipeline.write_art_pack(game.project_dir())


def _palette_changed(self, context):
    owner = self.id_data
    if isinstance(owner, bpy.types.Object) and owner.mt2.asset == "costume":
        show_palette(owner)


class MT2_Color(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR_GAMMA", size=4, min=0.0, max=1.0,
                                         update=_palette_changed)


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
    recent_colors: bpy.props.CollectionProperty(type=MT2_Color)
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
    show_notes: bpy.props.BoolProperty(name="Notes", description="Show Check's notes, not only its problems")
    show_guides: bpy.props.BoolProperty(
        name="Guides", default=True,
        description="Draw the 3 x 3 x 3 cell of modular pieces and the length of walls and bridges in the viewport",
    )
    art_pack: bpy.props.BoolProperty(
        name="Art pack", update=_art_pack_changed,
        description="Lock what this mod exports behind an art pack players buy in the Art Store. "
                    "Each export updates it",
    )
    art_pack_name: bpy.props.StringProperty(
        name="Name", description="The art pack's name in the Art Store", update=_art_pack_changed,
    )
    art_pack_description: bpy.props.StringProperty(
        name="Description", description="The text under the art pack's name in the Art Store",
        update=_art_pack_changed,
    )
    art_pack_cost: bpy.props.IntProperty(
        name="Cost", min=0, default=2000, update=_art_pack_changed,
        description="0 leaves the game's default",
    )
    art_pack_costumes: bpy.props.BoolProperty(
        name="Costumes", update=_art_pack_changed,
        description="Lock the mod's costumes behind the art pack too; otherwise they're available from the start",
    )
    weapon_packs: bpy.props.BoolProperty(
        name="Weapon packs", update=_art_pack_changed,
        description="Sell each new weapon category as its own weapon pack in the Art Store, like the game's Bows or Guns",
    )
    weapon_pack_cost: bpy.props.IntProperty(
        name="Cost", min=0, default=2000, update=_art_pack_changed, description="0 leaves the game's default",
    )
    art_pack_exotic: bpy.props.BoolProperty(
        name="Exotic", description="Listed as an exotic art pack", update=_art_pack_changed,
    )
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
    gizmo_dir: bpy.props.EnumProperty(name="Kind", items=gizmo_dir_items, update=_forget_findings)
    animation: bpy.props.EnumProperty(
        name="Animation", items=animation_items, update=_animation_changed,
        description="The animation shown on this model; keyframes you add go into it",
    )
    playback: bpy.props.EnumProperty(
        name="Playback", items=[(p, p, "") for p in PLAYBACK_TYPES], update=_playback_changed,
        description="How the game plays the animation: once, once and hold the last frame, loop, or back and forth",
    )
    bridge_piece: bpy.props.EnumProperty(
        name="Piece", items=(("bridge", "Bridge", ""), ("ramp", "Ramp", "")), default="bridge",
        update=_forget_findings,
    )
    dungeon_theme: bpy.props.StringProperty(name="Theme", update=_forget_findings)
    tile_kind: bpy.props.EnumProperty(
        name="Piece", items=(("walls", "Wall", ""), ("ceilings", "Ceiling", "")), default="walls",
        update=_forget_findings,
    )
    shape: bpy.props.EnumProperty(
        name="Shape", items=[(s, s.replace("_", " "), "") for s in SHAPES], default="N", update=_forget_findings,
        description="Which sides are open: N, E, S, W and the corners between them; O is a closed room piece",
    )
    socket_tags: bpy.props.StringProperty(
        name="Tags", description="Space-separated, such as: floor prop small. The dungeon adds its theme's name",
    )
    vehicle_kind: bpy.props.EnumProperty(
        name="Travels by", items=(("air", "Air", "An airship"), ("water", "Water", "A ship")), default="air",
        update=_forget_findings,
    )
    building_dir: bpy.props.EnumProperty(name="Building type", items=building_dir_items, update=_forget_findings)
    description: bpy.props.StringProperty(
        name="Description", update=_forget_findings, description="The text players see when hovering this vehicle",
    )
    display_name: bpy.props.StringProperty(
        name="Display name", update=_forget_findings,
        description="The name players see for this building, vehicle, costume or new weapon category",
    )
    raw_path: bpy.props.StringProperty(
        name="Game path", description="Relative path, e.g. scenery/stone/my_rock.vmb", update=_forget_findings,
    )
    role: bpy.props.EnumProperty(name="Role", items=ROLES, default="NONE")
    source_path: bpy.props.StringProperty(name="Imported from")
    source_variant: bpy.props.StringProperty(name="Variant template")
    exported_path: bpy.props.StringProperty(name="Exported as")
    palette: bpy.props.CollectionProperty(type=MT2_Color, description="The costume's 8 default colors")


class MT2_MaterialSettings(bpy.types.PropertyGroup):
    game_name: bpy.props.StringProperty(
        name="Game material", description="The materials/<name>.mat this slot exports as",
    )


CLASSES = (MT2_Finding, MT2_MaterialName, MT2_Color, MT2_SceneSettings, MT2_ObjectSettings, MT2_MaterialSettings)


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
