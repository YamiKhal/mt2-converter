from contextlib import contextmanager

import bmesh
import bpy
import numpy as np


class MeshOperator(bpy.types.Operator):
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(mesh_objects(context))

    def faces_to_change(self, context) -> bool:
        if context.mode != "EDIT_MESH" or any(_has_selected_face(o) for o in mesh_objects(context)):
            return True
        self.report({"WARNING"}, "No faces selected. Select faces, or go to Object Mode to change the whole mesh")

        return False


@contextmanager
def editable_mesh(obj):
    was_edit = obj.mode == "EDIT"
    if was_edit:
        bpy.ops.object.mode_set(mode="OBJECT")
    try:
        mesh = obj.data
        selected = np.empty(len(mesh.polygons), dtype=bool)
        mesh.polygons.foreach_get("select", selected)
        if not was_edit:
            selected[:] = True
        yield mesh, selected
        mesh.update()
    finally:
        if was_edit:
            bpy.ops.object.mode_set(mode="EDIT")


def mesh_objects(context) -> list[bpy.types.Object]:
    return [o for o in context.selected_objects if o.type == "MESH"] or (
        [context.active_object] if context.active_object and context.active_object.type == "MESH" else [])


def loop_faces(mesh) -> np.ndarray:
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)

    return np.repeat(np.arange(len(mesh.polygons)), totals)


def loop_vertices(mesh) -> np.ndarray:
    vertices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", vertices)

    return vertices


def color_attribute(mesh):
    attribute = mesh.color_attributes.active_color
    if attribute is None:
        attribute = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        attribute.data.foreach_set("color_srgb", [1.0] * 4 * len(mesh.loops))
        mesh.color_attributes.active_color = attribute
        mesh.color_attributes.render_color_index = mesh.color_attributes.active_color_index

    return attribute


def uv_layer(mesh):
    return mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")


def attribute_values(attribute) -> tuple[np.ndarray, bool]:
    values = np.empty(len(attribute.data) * 4, dtype=np.float32)
    attribute.data.foreach_get("color_srgb", values)

    return values.reshape(-1, 4), attribute.domain == "CORNER"


def corner_colors(mesh, attribute) -> np.ndarray:
    values, per_corner = attribute_values(attribute)

    return values if per_corner else values[loop_vertices(mesh)]


def face_colors(mesh, attribute) -> np.ndarray:
    faces = loop_faces(mesh)
    sums = np.zeros((len(mesh.polygons), 4))
    np.add.at(sums, faces, corner_colors(mesh, attribute))
    counts = np.bincount(faces, minlength=len(mesh.polygons))[:, None]

    return (sums / np.maximum(counts, 1)).astype(np.float32)


def _has_selected_face(obj) -> bool:
    if obj.mode != "EDIT":
        return False

    return any(face.select for face in bmesh.from_edit_mesh(obj.data).faces)
