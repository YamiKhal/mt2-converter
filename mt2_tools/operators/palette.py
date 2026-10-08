import bpy
import numpy as np

from ..mt2model.costume_parts import slot_u
from ..mt2model.materials import PALETTE_SLOTS
from ..objects.meshes import MeshOperator, editable_mesh, loop_faces, loop_vertices, mesh_objects, uv_layer


class MT2_OT_palette_slot(MeshOperator):
    bl_idname = "mt2.palette_slot"
    bl_label = "Palette slot"
    bl_description = "Color the selected faces with a costume (8) or dungeon (4) palette slot by setting their U"

    slot: bpy.props.IntProperty(name="Slot", min=1, max=8, default=1)

    def execute(self, context):
        if not self.faces_to_change(context):
            return {"CANCELLED"}
        for obj in mesh_objects(context):
            with editable_mesh(obj) as (mesh, selected):
                layer = uv_layer(mesh)
                uvs = np.empty(len(mesh.loops) * 2, dtype=np.float32)
                layer.data.foreach_get("uv", uvs)
                uvs = uvs.reshape(-1, 2)
                material_index = np.empty(len(mesh.polygons), dtype=np.int32)
                mesh.polygons.foreach_get("material_index", material_index)
                faces = loop_faces(mesh)
                for loop in np.nonzero(selected[faces])[0]:
                    slots = _slots(obj, int(material_index[faces[loop]]))
                    uvs[loop, 0] = slot_u((self.slot - 1) % slots, slots)
                layer.data.foreach_set("uv", uvs.ravel())
        context.scene.mt2.palette_slot = self.slot

        return {"FINISHED"}


def _slots(obj, index: int) -> int:
    material = obj.material_slots[index].material if index < len(obj.material_slots) else None
    kind = material.mt2.get("kind") if material else None

    return PALETTE_SLOTS.get(kind, 8)


class MT2_OT_shade(MeshOperator):
    bl_idname = "mt2.shade"
    bl_label = "Set shade"
    bl_description = "Set the palette shading (V) of the selected faces: 0 keeps the color, 1 halves it"

    gradient: bpy.props.BoolProperty(name="Gradient", description="Darker toward the bottom, like vanilla parts")

    def execute(self, context):
        if not self.faces_to_change(context):
            return {"CANCELLED"}
        settings = context.scene.mt2
        for obj in mesh_objects(context):
            with editable_mesh(obj) as (mesh, selected):
                layer = uv_layer(mesh)
                uvs = np.empty(len(mesh.loops) * 2, dtype=np.float32)
                layer.data.foreach_get("uv", uvs)
                uvs = uvs.reshape(-1, 2)
                loops = selected[loop_faces(mesh)]
                if self.gradient:
                    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
                    mesh.vertices.foreach_get("co", co)
                    height = co.reshape(-1, 3)[loop_vertices(mesh), 2]
                    span = max(float(height.max() - height.min()), 1e-6)
                    up = (height - height.min()) / span
                    shade = settings.shade_bottom + (settings.shade_top - settings.shade_bottom) * up
                    uvs[loops, 1] = shade[loops]
                else:
                    uvs[loops, 1] = settings.shade
                layer.data.foreach_set("uv", uvs.ravel())

        return {"FINISHED"}


CLASSES = (MT2_OT_palette_slot, MT2_OT_shade)
