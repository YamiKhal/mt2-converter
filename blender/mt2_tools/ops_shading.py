import bpy
import numpy as np

from .mesh_data import MeshOperator, editable_mesh, loop_faces, mesh_objects


class MT2_OT_flat_shading(MeshOperator):
    bl_idname = "mt2.flat_shading"
    bl_label = "Flat shading"
    bl_description = ("Shade the selected faces (edit mode) or the whole mesh flat, one normal per face, and drop "
                      "their custom normals. Fixes faces that shade in gradients because of smooth shading")

    def execute(self, context):
        if not self.faces_to_change(context):
            return {"CANCELLED"}
        for obj in mesh_objects(context):
            with editable_mesh(obj) as (mesh, selected):
                _shade_flat(context, obj, mesh, selected)

        return {"FINISHED"}


def _shade_flat(context, obj: bpy.types.Object, mesh: bpy.types.Mesh, selected: np.ndarray):
    corner_normals = np.empty(len(mesh.loops) * 3, dtype=np.float32)
    mesh.corner_normals.foreach_get("vector", corner_normals)
    smooth = np.empty(len(mesh.polygons), dtype=bool)
    mesh.polygons.foreach_get("use_smooth", smooth)
    smooth[selected] = False
    mesh.polygons.foreach_set("use_smooth", smooth)
    if not mesh.has_custom_normals:
        return
    if selected.all():
        with context.temp_override(object=obj, active_object=obj, selected_editable_objects=[obj]):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        return
    face_normals = np.empty(len(mesh.polygons) * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", face_normals)
    corner_normals = corner_normals.reshape(-1, 3)
    faces = loop_faces(mesh)
    flat = selected[faces]
    corner_normals[flat] = face_normals.reshape(-1, 3)[faces[flat]]
    mesh.normals_split_custom_set(corner_normals.tolist())


CLASSES = (MT2_OT_flat_shading,)
