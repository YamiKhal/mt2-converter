from pathlib import Path

import bpy
import numpy as np
from bpy_extras.io_utils import ImportHelper

from .. import game, mod_folder
from ..conversion.to_game import asset_root
from ..materials.game_materials import material_for
from ..materials.palette import show_palette
from ..materials.textured import TEXTURE_SUFFIXES, write_textured_material
from ..mt2model.glow import COSTUME_SHADER, glow_material, glow_shader
from ..mt2model.naming import prefixed
from ..objects.costumes import costume_root
from ..objects.meshes import color_attribute, editable_mesh

GLOW_NAME = "costume_glow"

_material_items: list = []


def _assign(obj: bpy.types.Object, slot: int, material: bpy.types.Material):
    if obj.mode != "EDIT":
        color_attribute(obj.data)
    if not obj.material_slots:
        obj.data.materials.append(material)
    else:
        obj.material_slots[min(slot, len(obj.material_slots) - 1)].material = material


def _game_material_items(self, context):
    data = game.game_data()
    _material_items.clear()
    _material_items.extend((name, name, "") for name in sorted(data.materials() if data else ()))

    return _material_items or [("", "Set the game folder first", "")]


class _MeshOperator(bpy.types.Operator):
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"


class MT2_OT_setup_material(_MeshOperator):
    bl_idname = "mt2.setup_material"
    bl_label = "Use game material"
    bl_description = "Put this game material in the active slot, with a preview that looks like the game"

    name: bpy.props.StringProperty(name="Game material", default="Material_tint")

    def execute(self, context):
        catalog = game.catalog()
        obj = context.active_object
        _assign(obj, obj.active_material_index, material_for(self.name))
        if catalog is None or catalog.get(self.name) is None:
            self.report({"WARNING"}, f"'{self.name}' is not a game or mod material")

        return {"FINISHED"}


class MT2_OT_pick_game_material(_MeshOperator):
    bl_idname = "mt2.pick_game_material"
    bl_label = "Pick game material"
    bl_description = (
        "Choose the game material for this slot. Only this slot changes; other objects keep their materials"
    )
    bl_property = "name"

    slot: bpy.props.IntProperty()
    name: bpy.props.EnumProperty(name="Game material", items=_game_material_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)

        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not self.name:
            return {"CANCELLED"}
        _assign(context.active_object, self.slot, material_for(self.name))

        return {"FINISHED"}


class MT2_OT_new_textured_material(_MeshOperator, ImportHelper):
    bl_idname = "mt2.new_textured_material"
    bl_label = "New textured material"
    bl_description = (
        "Copy an image into the mod, write a textured material for it and put it in the active slot. "
        "White vertex colors show the texture as it is; other colors tint it"
    )

    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.bmp", options={"HIDDEN"})
    material_name: bpy.props.StringProperty(
        name="Name", description="Becomes <mod id>_<name>; empty uses the image name"
    )

    def execute(self, context):
        folder = game.project_dir()
        mod_id = context.scene.mt2.mod_id
        source = Path(self.filepath)
        if folder is None or not mod_id:
            self.report({"ERROR"}, "Set the mod folder and mod id first")
            return {"CANCELLED"}
        if source.suffix.lower() not in TEXTURE_SUFFIXES or not source.is_file():
            self.report({"ERROR"}, "Pick a PNG, JPG, TGA or BMP image")
            return {"CANCELLED"}
        try:
            name = write_textured_material(
                folder, mod_id, self.material_name or source.stem, source.read_bytes(), source.suffix
            )
        except FileExistsError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        obj = context.active_object
        _assign(obj, obj.active_material_index, material_for(name))
        self.report({"INFO"}, f"Wrote materials/{name}.mat and its texture")

        return {"FINISHED"}


class MT2_OT_costume_glow(_MeshOperator):
    bl_idname = "mt2.costume_glow"
    bl_label = "Glow"
    bl_description = (
        "Make the selected faces (edit mode) or the whole mesh glow in their palette color, by day "
        "and by night. Writes the mod's glowing costume material and its shader"
    )

    @classmethod
    def poll(cls, context):
        return super().poll(context) and is_costume_mesh(context.active_object)

    def execute(self, context):
        folder = game.project_dir()
        mod_id = context.scene.mt2.mod_id
        data = game.game_data()
        if folder is None or not mod_id or data is None:
            self.report({"ERROR"}, "Set the game folder, the mod folder and the mod id first")
            return {"CANCELLED"}
        name = prefixed(mod_id, GLOW_NAME)
        try:
            _write_glow_files(folder, name, data.sources[-1])
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        obj = context.active_object
        material = material_for(name)
        with editable_mesh(obj) as (mesh, selected):
            color_attribute(mesh)
            if not mesh.materials:
                mesh.materials.append(material_for("costume"))
            if material.name not in mesh.materials:
                mesh.materials.append(material)
            slots = np.empty(len(mesh.polygons), dtype=np.int32)
            mesh.polygons.foreach_get("material_index", slots)
            slots[selected] = mesh.materials.find(material.name)
            mesh.polygons.foreach_set("material_index", slots)
        costume = costume_root(obj)
        if costume is not None:
            show_palette(costume)

        return {"FINISHED"}


def is_costume_mesh(obj: bpy.types.Object) -> bool:
    root = asset_root(obj)

    return costume_root(obj) is not None or (root is not None and root.mt2.asset == "costume_part")


def _write_glow_files(folder: Path, name: str, vanilla):
    shader = f"{name}_f.glsl"
    files = {
        f"materials/{name}.mat": glow_material(vanilla.read("materials/costume.mat").decode(), shader),
        f"shaders/{shader}": glow_shader(vanilla.read(f"shaders/{COSTUME_SHADER}").decode()),
    }
    changed = [rel for rel, text in files.items() if mod_folder.read_text(folder, rel) != text]
    for rel in changed:
        mod_folder.write_text(folder, rel, files[rel])
    if changed:
        game.forget()


CLASSES = (MT2_OT_setup_material, MT2_OT_pick_game_material, MT2_OT_new_textured_material, MT2_OT_costume_glow)
