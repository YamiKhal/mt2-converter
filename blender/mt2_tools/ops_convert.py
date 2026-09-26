import os
import tempfile

import bpy
from mathutils import Matrix, Vector

from . import game
from .game_materials import material_for
from .mt2model.assets import ASSET_TYPES, PLACEABLE_SCENERY_TYPES
from .mt2model.naming import clean_word
from .textured_materials import write_textured_material

TARGETS = ("scenery", "tagged", "weapon", "building", "vehicle")
HEIGHTS = {"scenery": 4.0, "tagged": 2.0, "weapon": 1.4, "building": 20.0, "vehicle": 12.0}


def _target_changed(self, context):
    self.height = HEIGHTS.get(self.target, 4.0)
    self.faces = min(ASSET_TYPES[self.target].budget // 3, 4000)


class MT2_OT_convert(bpy.types.Operator):
    bl_idname = "mt2.convert"
    bl_label = "Convert"
    bl_description = ("Turn the selected imported model (glTF, FBX, OBJ, …) into a game asset in one step: "
                      "join, apply transforms, scale, set the origin at its base, reduce, and color it")
    bl_options = {"REGISTER", "UNDO"}

    target: bpy.props.EnumProperty(
        name="Becomes", items=[(t, ASSET_TYPES[t].label, ASSET_TYPES[t].description) for t in TARGETS],
        default="scenery", update=_target_changed,
    )
    scenery_type: bpy.props.EnumProperty(
        name="Scenery type", items=[(t, t.replace("_", " ").capitalize(), "") for t in PLACEABLE_SCENERY_TYPES],
        default="prop",
    )
    height: bpy.props.FloatProperty(name="Height", min=0.01, default=4.0, description="A character is about 2 tall")
    faces: bpy.props.IntProperty(name="Faces", min=4, default=2000, description="Reduce to about this many faces")
    colors: bpy.props.EnumProperty(
        name="Colors",
        items=(("BAKE", "Bake texture", "Bake the look into vertex colors, the game's usual style"),
               ("TEXTURE", "Keep texture", "Keep its texture with a textured material"),
               ("KEEP", "Keep vertex colors", "It already has vertex colors")),
        default="BAKE",
    )
    name: bpy.props.StringProperty(name="Name")

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects) and context.mode == "OBJECT"

    def invoke(self, context, event):
        _target_changed(self, context)
        self.name = clean_word(context.active_object.name) if context.active_object else "model"

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "name")
        layout.prop(self, "target")
        if self.target == "scenery":
            layout.prop(self, "scenery_type")
        layout.prop(self, "height")
        layout.prop(self, "faces")
        layout.prop(self, "colors")

    def execute(self, context):
        obj = _join(context)
        _apply_transforms(obj)
        _scale_and_ground(obj, self.height)
        _decimate(obj, self.faces)
        if self.colors == "BAKE":
            bpy.ops.mt2.bake_colors()
            _use_only(obj, material_for("Material_tint"))
        elif self.colors == "TEXTURE":
            if not self._texture(context, obj):
                return {"CANCELLED"}
        else:
            _use_only(obj, material_for("Material_tint"))
        bpy.ops.mt2.make_asset()
        obj.mt2.asset = self.target
        obj.mt2.name = clean_word(self.name) or "model"
        if self.target == "scenery":
            obj.mt2.scenery_type = self.scenery_type
        bpy.ops.mt2.check()

        return {"FINISHED"}

    def _texture(self, context, obj) -> bool:
        image = _first_image(obj)
        folder = game.project_dir()
        if image is None or folder is None or not context.scene.mt2.mod_id:
            self.report({"ERROR"}, "No image texture found, or the mod folder and id aren't set")
            return False
        try:
            name = write_textured_material(folder, context.scene.mt2.mod_id, self.name, _image_bytes(image), ".png")
        except FileExistsError as error:
            self.report({"ERROR"}, str(error))
            return False
        _use_only(obj, material_for(name))
        _white_colors(obj)

        return True


def _join(context) -> bpy.types.Object:
    meshes = [o for o in context.selected_objects if o.type == "MESH"]
    active = context.active_object if context.active_object in meshes else meshes[0]
    for obj in context.selected_objects:
        obj.select_set(obj in meshes)
    context.view_layer.objects.active = active
    if len(meshes) > 1:
        bpy.ops.object.join()

    return context.view_layer.objects.active


def _apply_transforms(obj: bpy.types.Object):
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world
    obj.data.transform(Matrix.LocRotScale(None, world.to_quaternion(), world.to_scale()))
    obj.matrix_world = Matrix.Translation(world.translation)


def _scale_and_ground(obj: bpy.types.Object, height: float):
    points = [v.co for v in obj.data.vertices]
    if not points:
        return
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    size = high.z - low.z
    factor = height / size if size > 0 else 1.0
    base = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    obj.data.transform(Matrix.Scale(factor, 4) @ Matrix.Translation(-base))
    obj.data.update()


def _decimate(obj: bpy.types.Object, faces: int):
    count = len(obj.data.polygons)
    if count <= faces:
        return
    modifier = obj.modifiers.new("MT2 Decimate", "DECIMATE")
    modifier.ratio = max(faces / count, 0.001)


def _use_only(obj: bpy.types.Object, material: bpy.types.Material):
    obj.data.materials.clear()
    obj.data.materials.append(material)


def _first_image(obj: bpy.types.Object) -> bpy.types.Image | None:
    for slot in obj.material_slots:
        tree = slot.material.node_tree if slot.material and slot.material.node_tree else None
        for node in tree.nodes if tree else []:
            if node.type == "TEX_IMAGE" and node.image is not None:
                return node.image

    return None


def _image_bytes(image: bpy.types.Image) -> bytes:
    handle, path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    try:
        copy = image.copy()
        copy.filepath_raw = path
        copy.file_format = "PNG"
        copy.save()
        bpy.data.images.remove(copy)
        with open(path, "rb") as file:
            return file.read()
    finally:
        os.remove(path)


def _white_colors(obj: bpy.types.Object):
    mesh = obj.data
    for attribute in list(mesh.color_attributes):
        mesh.color_attributes.remove(attribute)


CLASSES = (MT2_OT_convert,)
