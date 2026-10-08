from collections import deque

import bpy
import numpy as np

from ..objects.meshes import editable_mesh, face_colors, loop_faces


class MT2_OT_select_color(bpy.types.Operator):
    bl_idname = "mt2.select_color"
    bl_label = "Select same color"
    bl_description = (
        "Select the faces with the same color as the selected ones: the ones touching them, "
        "or every one in the mesh when Connected only is disabled"
    )
    bl_options = {"REGISTER", "UNDO"}

    tolerance: bpy.props.FloatProperty(
        name="Tolerance",
        description="How far a color may differ, per channel (0 to 1)",
        min=0.0,
        max=1.0,
        default=0.02,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object

        return context.mode == "EDIT_MESH" and obj is not None and obj.data.color_attributes.active_color is not None

    def execute(self, context):
        connected = context.scene.mt2.select_connected
        with editable_mesh(context.active_object) as (mesh, _):
            seeds = np.empty(len(mesh.polygons), dtype=bool)
            mesh.polygons.foreach_get("select", seeds)
            if not seeds.any():
                self.report({"WARNING"}, "Select at least one face first")
                return {"CANCELLED"}
            colors = face_colors(mesh, mesh.color_attributes.active_color)
            matching = _matching(colors, colors[seeds], self.tolerance)
            chosen = _grow(mesh, seeds, matching) if connected else matching | seeds
            _select_faces(mesh, chosen)
        self.report({"INFO"}, f"{int(chosen.sum())} faces selected")

        return {"FINISHED"}


def _matching(colors: np.ndarray, targets: np.ndarray, tolerance: float) -> np.ndarray:
    matching = np.zeros(len(colors), dtype=bool)
    for target in np.unique(np.round(targets * 255), axis=0) / 255:
        matching |= np.abs(colors - target).max(axis=1) <= tolerance + 0.5 / 255

    return matching


def _grow(mesh, seeds: np.ndarray, matching: np.ndarray) -> np.ndarray:
    neighbours = _face_neighbours(mesh)
    chosen = seeds.copy()
    queue = deque(np.flatnonzero(seeds))
    while queue:
        face = queue.popleft()
        for other in neighbours[face]:
            if matching[other] and not chosen[other]:
                chosen[other] = True
                queue.append(other)

    return chosen


def _face_neighbours(mesh) -> list[list[int]]:
    edges = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("edge_index", edges)
    faces_of_edge: dict[int, list[int]] = {}
    for edge, face in zip(edges.tolist(), loop_faces(mesh).tolist()):
        faces_of_edge.setdefault(edge, []).append(face)
    neighbours: list[list[int]] = [[] for _ in mesh.polygons]
    for faces in faces_of_edge.values():
        for face in faces:
            neighbours[face].extend(f for f in faces if f != face)

    return neighbours


def _select_faces(mesh, chosen: np.ndarray) -> None:
    faces = loop_faces(mesh)
    vertices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", vertices)
    edges = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("edge_index", edges)
    vertex_selected = np.zeros(len(mesh.vertices), dtype=bool)
    vertex_selected[vertices[chosen[faces]]] = True
    edge_selected = np.zeros(len(mesh.edges), dtype=bool)
    edge_selected[edges[chosen[faces]]] = True
    mesh.vertices.foreach_set("select", vertex_selected)
    mesh.edges.foreach_set("select", edge_selected)
    mesh.polygons.foreach_set("select", chosen)


CLASSES = (MT2_OT_select_color,)
