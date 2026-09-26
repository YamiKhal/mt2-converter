import bpy

from . import game
from .anim_objects import REST_POSE
from .costume_objects import costume_root
from .mt2model.naming import clean_word
from .rig_objects import (add_bone, game_rigs, keep_rest_pose, name_problem, rename_bone, rig_name, skeleton_root,
                          starting_animations)


def _select(context, obj):
    for other in context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


class MT2_OT_add_bone(bpy.types.Operator):
    bl_idname = "mt2.add_bone"
    bl_label = "Add bone"
    bl_description = ("Add a bone at the 3D cursor, parented to the selected bone. Parts parented to it follow it, "
                      "and animations can move it")
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Name", default="wingleft")

    @classmethod
    def poll(cls, context):
        return costume_root(context.active_object) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        costume = costume_root(context.active_object)
        name = clean_word(self.name)
        problem = name_problem(costume, None, name)
        if problem:
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        active = context.active_object
        parent = active if active.mt2.role == "BONE" else skeleton_root(costume)
        context.view_layer.update()
        _select(context, add_bone(parent, name, context.scene.cursor.location))

        return {"FINISHED"}


def _own_rig_problem(context, costume) -> str | None:
    data = game.game_data()
    if data is None:
        return "Set the game folder in the add-on preferences first"
    if rig_name(costume, context.scene.mt2.mod_id, game_rigs(data)) in game_rigs(data):
        return "The game's rigs keep their bones as they are; give the costume its own Rig name first"

    return None


class MT2_OT_rename_bone(bpy.types.Operator):
    bl_idname = "mt2.rename_bone"
    bl_label = "Rename bone"
    bl_description = ("Rename the selected bone. Its animations, parts and the costume's entries follow, and so do "
                      "the mod's other costumes on this rig when you export")
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Name")

    @classmethod
    def poll(cls, context):
        obj = context.active_object

        return obj is not None and obj.mt2.role == "BONE" and costume_root(obj) is not None

    def invoke(self, context, event):
        self.name = context.active_object.get("mt2_node", context.active_object.name)

        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        bone = context.active_object
        costume = costume_root(bone)
        name = clean_word(self.name)
        if name == bone.get("mt2_node", bone.name):
            return {"CANCELLED"}
        problem = _own_rig_problem(context, costume) or name_problem(costume, bone, name)
        if problem:
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        rename_bone(costume, bone, name)

        return {"FINISHED"}


class MT2_OT_set_rest_pose(bpy.types.Operator):
    bl_idname = "mt2.set_rest_pose"
    bl_label = "Set rest pose"
    bl_description = ("Keep the bones you moved where they are now. The costume's animations move them "
                      "from their new place")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return costume_root(context.active_object) is not None

    def execute(self, context):
        costume = costume_root(context.active_object)
        problem = _own_rig_problem(context, costume)
        if problem:
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        rig = rig_name(costume, context.scene.mt2.mod_id, game_rigs(game.game_data()))
        kept = keep_rest_pose(costume, starting_animations(costume, rig))
        if not kept:
            self.report({"INFO"}, "No bone was moved")
            return {"FINISHED"}
        costume.mt2.animation = REST_POSE
        self.report({"INFO"}, f"Kept {', '.join(kept)}")

        return {"FINISHED"}


CLASSES = (MT2_OT_add_bone, MT2_OT_rename_bone, MT2_OT_set_rest_pose)
