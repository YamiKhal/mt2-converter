import bpy
import numpy as np

from .mesh_data import color_attribute, editable_mesh, face_colors


class MT2_OT_use_color(bpy.types.Operator):
    bl_idname = "mt2.use_color"
    bl_label = "Use color"
    bl_description = "Make this recently used color the paint color"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        recent = context.scene.mt2.recent_colors
        if not 0 <= self.index < len(recent):
            return {"CANCELLED"}
        context.scene.mt2.paint_color = recent[self.index].color

        return {"FINISHED"}


class MT2_OT_pick_color(bpy.types.Operator):
    bl_idname = "mt2.pick_color"
    bl_label = "Pick"
    bl_description = "Make the color of the active face (edit mode) the paint color"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        obj = context.active_object
        with editable_mesh(obj) as (mesh, _):
            chosen = np.empty(len(mesh.polygons), dtype=bool)
            mesh.polygons.foreach_get("select", chosen)
            face = mesh.polygons.active
            if not (0 <= face < len(mesh.polygons) and chosen[face]):
                face = int(np.flatnonzero(chosen)[0]) if chosen.any() else -1
            if face < 0 or mesh.color_attributes.active_color is None:
                self.report({"WARNING"}, "Select a painted face first")
                return {"CANCELLED"}
            color = face_colors(mesh, color_attribute(mesh))[face]
        context.scene.mt2.paint_color = tuple(float(c) for c in color)
        self.report({"INFO"}, "Picked #" + "".join(f"{round(c * 255):02X}" for c in color[:3]))

        return {"FINISHED"}


CLASSES = (MT2_OT_use_color, MT2_OT_pick_color)
