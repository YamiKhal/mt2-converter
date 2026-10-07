import bpy

from .mesh_data import (MeshOperator, attribute_values, color_attribute, editable_mesh, face_colors, loop_faces,
                        loop_vertices, mesh_objects)
from .mt2model.colors import srgb_to_linear
from .recent_colors import remember_color


class MT2_OT_fill_color(MeshOperator):
    bl_idname = "mt2.fill_color"
    bl_label = "Fill"
    bl_description = ("Paint the selected faces (edit mode) or the whole mesh with the color. A point light takes it "
                      "as its color")

    def execute(self, context):
        if not self.faces_to_change(context):
            return {"CANCELLED"}
        color = tuple(context.scene.mt2.paint_color)
        for obj in mesh_objects(context):
            if obj.mt2.role == "LIGHT":
                obj.color = srgb_to_linear(color)
                continue
            with editable_mesh(obj) as (mesh, selected):
                attribute = color_attribute(mesh)
                values, per_corner = attribute_values(attribute)
                loops = selected[loop_faces(mesh)]
                if per_corner:
                    values[loops] = color
                else:
                    values[loop_vertices(mesh)[loops]] = color
                attribute.data.foreach_set("color_srgb", values.ravel())
        remember_color(context.scene, color)

        return {"FINISHED"}


class MT2_OT_flat_colors(MeshOperator):
    bl_idname = "mt2.flat_colors"
    bl_label = "Flat colors"
    bl_description = "Give every selected face one color, the average of its corners (the MT2 low-poly look)"

    def execute(self, context):
        if not self.faces_to_change(context):
            return {"CANCELLED"}
        for obj in mesh_objects(context):
            if obj.mt2.role == "LIGHT":
                obj.color = srgb_to_linear(color)
                continue
            with editable_mesh(obj) as (mesh, selected):
                attribute = color_attribute(mesh)
                if attribute.domain != "CORNER":
                    self.report({"WARNING"}, f"'{obj.name}' has per-vertex colors; convert them to face corners first")
                    continue
                values, _ = attribute_values(attribute)
                faces = loop_faces(mesh)
                loops = selected[faces]
                values[loops] = face_colors(mesh, attribute)[faces[loops]]
                attribute.data.foreach_set("color_srgb", values.ravel())

        return {"FINISHED"}


class MT2_OT_bake_colors(MeshOperator):
    bl_idname = "mt2.bake_colors"
    bl_label = "Bake textures to colors"
    bl_description = ("Bake each selected object's material color (textures included) into its vertex colors "
                      "with Cycles. Afterwards assign MT2 materials; the textures themselves are not exported")

    flat: bpy.props.BoolProperty(name="Flat colors afterwards", default=True)

    def execute(self, context):
        scene = context.scene
        engine = scene.render.engine
        samples = scene.cycles.samples if hasattr(scene, "cycles") else None
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            scene.render.engine = "CYCLES"
            scene.cycles.samples = 4
            for obj in mesh_objects(context):
                color_attribute(obj.data)
            bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, target="VERTEX_COLORS")
        except RuntimeError as error:
            self.report({"ERROR"}, f"Bake failed: {error}")
            return {"CANCELLED"}
        finally:
            scene.render.engine = engine
            if samples is not None:
                scene.cycles.samples = samples
        if self.flat:
            bpy.ops.mt2.flat_colors()

        return {"FINISHED"}


CLASSES = (MT2_OT_fill_color, MT2_OT_flat_colors, MT2_OT_bake_colors)
