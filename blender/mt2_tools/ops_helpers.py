import math

import bpy
from mathutils import Matrix, Vector

from . import convert_out, game, shading
from .convert_out import asset_root
from .bridge_objects import NEW_RAMP_PATH, create_ramp_path, is_ramp, ramp_path_object
from .creature_spot import create_spot, is_flight_point, spot_of
from .mt2model.assets import asset_type
from .mt2model.axes import swap_ground
from .mt2model.costume import read_defaults
from .mt2model.footprint import building_footprint, scenery_footprint
from .mt2model.naming import clean_word
from .pad_objects import new_entrance, new_pad
from .socket_objects import new_socket

LIGHT_RADIUS_PER_DIAGONAL = 0.375
PAD_ASSETS = ("building", "vehicle")

_costume_items: list = []


def _helper(context, name: str, mesh, role: str, parent):
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.mt2.role = role
    obj.display_type = "WIRE"
    obj.hide_render = True

    return obj


class MT2_OT_make_asset(bpy.types.Operator):
    bl_idname = "mt2.make_asset"
    bl_label = "Make asset"
    bl_description = "Mark the active object as the root of an exportable model; its children export with it"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        obj.mt2.is_asset = True
        obj.mt2.role = "NONE"
        if not obj.mt2.name:
            obj.mt2.name = clean_word(obj.name)
        obj.mt2.normalise = True
        if obj.parent is not None and obj.parent.mt2.role == "BONE":
            obj.mt2.asset = "costume_part"
            obj.mt2.bone = obj.parent.get("mt2_node", obj.parent.name)

        return {"FINISHED"}


class MT2_OT_add_light(bpy.types.Operator):
    bl_idname = "mt2.add_light"
    bl_label = "Add point light"
    bl_description = "Add a helper box that becomes a scenery point light at its centre; its color is the object color"
    bl_options = {"REGISTER", "UNDO"}

    radius: bpy.props.FloatProperty(name="Radius", description="Vanilla lamps reach 35 to 50", min=0.1, default=45.0)
    color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR", size=4, min=0, max=1, default=(0.81, 0.43, 0.007, 1.0))

    @classmethod
    def poll(cls, context):
        return asset_root(context.active_object) is not None

    def execute(self, context):
        half = self.radius / LIGHT_RADIUS_PER_DIAGONAL / (2 * math.sqrt(3))
        corners = [(x, y, z) for x in (-half, half) for y in (-half, half) for z in (-half, half)]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        mesh = bpy.data.meshes.new("MT2 light")
        mesh.from_pydata(corners, [], faces)
        obj = _helper(context, "Point light", mesh, "LIGHT", asset_root(context.active_object))
        obj.location = context.scene.cursor.location
        obj.color = self.color

        return {"FINISHED"}


class MT2_OT_add_obstruction(bpy.types.Operator):
    bl_idname = "mt2.add_obstruction"
    bl_label = "Add obstruction shape"
    bl_description = ("Add a flat shape at ground level. Every face of it becomes one convex footprint polygon. "
                      "For scenery they replace the automatic footprint; under a bridge, nothing can be placed there")
    bl_options = {"REGISTER", "UNDO"}

    size: bpy.props.FloatProperty(name="Size", min=0.1, default=4.0)

    @classmethod
    def poll(cls, context):
        return asset_root(context.active_object) is not None

    def execute(self, context):
        root = asset_root(context.active_object)
        h = self.size / 2
        mesh = bpy.data.meshes.new("MT2 obstruction")
        mesh.from_pydata([(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)], [], [(0, 1, 2, 3)])
        obj = _helper(context, "Obstruction", mesh, "OBSTRUCTION", root)
        obj.location = (context.scene.cursor.location.x, context.scene.cursor.location.y, root.matrix_world.translation.z)

        return {"FINISHED"}


class MT2_OT_add_ramp_path(bpy.types.Operator):
    bl_idname = "mt2.add_ramp_path"
    bl_label = "Add ramp path"
    bl_description = ("Add the line characters walk up this ramp: from the ground at its start to the bridge at its end. "
                      "Its last point sets the bridge's height")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and is_ramp(root) and ramp_path_object(root) is None

    def execute(self, context):
        root = asset_root(context.active_object)
        _select(context, create_ramp_path(root, NEW_RAMP_PATH, context.collection))

        return {"FINISHED"}


class MT2_OT_add_pad(bpy.types.Operator):
    bl_idname = "mt2.add_pad"
    bl_label = "Add pad"
    bl_description = "Add an NPC pad at the 3D cursor, on the building's ground level. NPCs stand on pads"
    bl_options = {"REGISTER", "UNDO"}

    size: bpy.props.FloatProperty(name="Size", min=0.2, default=2.0)

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and root.mt2.asset in PAD_ASSETS

    def execute(self, context):
        root = asset_root(context.active_object)
        cursor = context.scene.cursor.location
        location = Vector((cursor.x, cursor.y, root.matrix_world.translation.z))
        pad = new_pad(root, location, self.size, context.collection)
        new_entrance(pad, context.collection)
        _select(context, pad)

        return {"FINISHED"}


class MT2_OT_add_entrance(bpy.types.Operator):
    bl_idname = "mt2.add_entrance"
    bl_label = "Add entrance"
    bl_description = "Add a path to the selected pad. NPCs walk it from its first point, outside, to the pad"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object

        return obj is not None and obj.mt2.role in ("PAD", "ENTRANCE")

    def execute(self, context):
        obj = context.active_object
        pad = obj if obj.mt2.role == "PAD" else obj.parent
        _select(context, new_entrance(pad, context.collection))

        return {"FINISHED"}


def _select(context, obj):
    for other in context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


class MT2_OT_add_creature_spot(bpy.types.Operator):
    bl_idname = "mt2.add_creature_spot"
    bl_label = "Add creature spot"
    bl_description = "Add where the flight point's creature stands, at the 3D cursor. Rotate it to turn the creature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and is_flight_point(root) and spot_of(root) is None

    def execute(self, context):
        root = asset_root(context.active_object)
        context.view_layer.update()
        spot = create_spot(root, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), context.collection)
        spot.location = spot.parent.matrix_world.inverted() @ context.scene.cursor.location
        _select(context, spot)

        return {"FINISHED"}


class MT2_OT_add_socket(bpy.types.Operator):
    bl_idname = "mt2.add_socket"
    bl_label = "Add socket"
    bl_description = "Add a prop socket at the 3D cursor. The dungeon places a prop whose tags match the socket's"
    bl_options = {"REGISTER", "UNDO"}

    tags: bpy.props.StringProperty(name="Tags", default="floor prop")

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and root.mt2.asset == "dungeon_tile"

    def execute(self, context):
        root = asset_root(context.active_object)
        socket = new_socket(root, Matrix.Translation(context.scene.cursor.location), self.tags, context.collection)
        _select(context, socket)

        return {"FINISHED"}


class MT2_OT_footprint_preview(bpy.types.Operator):
    bl_idname = "mt2.footprint_preview"
    bl_label = "Show footprint"
    bl_description = "Draw the footprint the game will compute for this scenery or building"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and root.mt2.asset in ("scenery", "building")

    def execute(self, context):
        root = asset_root(context.active_object)
        built = convert_out.build(root, asset_type(root.mt2.asset), game.catalog())
        polygon = building_footprint(built.root) if root.mt2.asset == "building" else scenery_footprint(built.root)
        for child in list(root.children):
            if child.mt2.role == "PREVIEW":
                bpy.data.objects.remove(child)
        if built.obstruction:
            self.report({"INFO"}, "This model has obstruction shapes; the game uses those instead")
            return {"FINISHED"}
        if polygon is None:
            self.report({"INFO"}, "No footprint: NPCs walk through this model")
            return {"FINISHED"}
        mesh = bpy.data.meshes.new("MT2 footprint")
        mesh.from_pydata([(*swap_ground(point), 0.02) for point in reversed(polygon)], [], [tuple(range(len(polygon)))])
        obj = _helper(context, f"{root.name} footprint", mesh, "PREVIEW", root)
        obj.matrix_parent_inverse.identity()
        obj.matrix_world = root.matrix_world if root.get("mt2_trs") else Matrix.Translation(root.matrix_world.translation)
        obj.hide_select = True

        return {"FINISHED"}


def _costumes(self, context):
    data = game.game_data()
    if data is not None and not _costume_items:
        _costume_items.extend((rel, rel.split("/")[-1][:-9], "") for rel in data.files("costumes/", ".defaults"))

    return _costume_items or [("", "Set the game folder first", "")]


class MT2_OT_palette_preview(bpy.types.Operator):
    bl_idname = "mt2.palette_preview"
    bl_label = "Preview palette"
    bl_description = "Show the palette of a costume's .defaults on this object's costume materials (preview only)"
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "costume"

    costume: bpy.props.EnumProperty(name="Costume", items=_costumes)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)

        return {"RUNNING_MODAL"}

    def execute(self, context):
        data = game.game_data()
        if data is None or not self.costume:
            return {"CANCELLED"}
        palette = read_defaults(data.read(self.costume))
        for slot in context.active_object.material_slots:
            if slot.material is not None:
                shading.set_palette(slot.material, palette)

        return {"FINISHED"}


CLASSES = (MT2_OT_make_asset, MT2_OT_add_light, MT2_OT_add_obstruction, MT2_OT_add_ramp_path, MT2_OT_add_pad, MT2_OT_add_entrance,
           MT2_OT_add_creature_spot, MT2_OT_add_socket, MT2_OT_footprint_preview,
           MT2_OT_palette_preview)
