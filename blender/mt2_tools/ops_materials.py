import shutil
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from . import game, project
from .game_materials import material_for
from .mt2model.naming import clean_word, prefixed

TEXTURE_FOLDER = "textures"
TEXTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tga", ".bmp")

_material_items: list = []


def _assign(obj: bpy.types.Object, slot: int, material: bpy.types.Material):
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
    bl_description = ("Choose the game material for this slot. Only this slot changes; "
                      "other objects keep their materials")
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
    bl_description = ("Copy an image into the mod, write a textured material for it and put it in the active slot. "
                      "White vertex colors show the texture as it is; other colors tint it")

    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.bmp", options={"HIDDEN"})
    material_name: bpy.props.StringProperty(name="Name", description="Becomes <mod id>_<name>; empty uses the image name")

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
        name = prefixed(mod_id, clean_word(self.material_name) or clean_word(source.stem))
        texture_rel = f"{TEXTURE_FOLDER}/{name}{source.suffix.lower()}"
        material_rel = f"materials/{name}.mat"
        if (folder / material_rel).exists():
            self.report({"ERROR"}, f"{material_rel} already exists; pick another name")
            return {"CANCELLED"}
        (folder / TEXTURE_FOLDER).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, folder / texture_rel)
        project.write_text(folder, material_rel, textured_material(texture_rel))
        game.forget()
        obj = context.active_object
        _assign(obj, obj.active_material_index, material_for(name))
        self.report({"INFO"}, f"Wrote {material_rel} and {texture_rel}")

        return {"FINISHED"}


def textured_material(texture_rel: str) -> str:
    return ("Material {\n"
            "\tcolor 1.0 1.0 1.0 1.0\n"
            "\tmode lit\n"
            f"\ttexture \"{texture_rel}\"\n"
            "\tshader \"tint_v.glsl\" \"tint_f.glsl\"\n"
            "}\n")


CLASSES = (MT2_OT_setup_material, MT2_OT_pick_game_material, MT2_OT_new_textured_material)
