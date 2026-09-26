import re
from dataclasses import dataclass, field

import bpy
import numpy as np
from mathutils import Matrix

from .convert_in import ORIGINAL_NORMALS, ORIGINAL_POSITIONS
from .mt2model.assets import AssetType
from .mt2model.axes import swap_ground, swap_position, swap_rotation, swap_scale
from .mt2model.colors import linear_to_srgb
from .mt2model.formats import make_format
from .mt2model.materials import MaterialCatalog
from .mt2model.model import Fragment, Node
from .mt2model.validate import MAX_VERTICES


@dataclass
class Built:
    root: Node
    obstruction: list[list[tuple[float, float]]] = field(default_factory=list)
    notes: list[tuple[str, str, str]] = field(default_factory=list)


GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
SKIPPED_ROLES = {"REFERENCE", "PREVIEW", "PAD", "ENTRANCE", "BONE", "SOCKET", "CREATURE"}
ROLE_MATERIAL = {"LIGHT": "light", "COLLISION": "collision", "NAVMESH": "navmesh"}
DEFAULT_MATERIAL = {"vertex": "Material_tint", "costume": "costume", "any": "Material_tint"}
DEGENERATE_RATIO = 1e-9


def build(root_obj: bpy.types.Object, asset: AssetType, catalog: MaterialCatalog | None) -> Built:
    built = Built(Node(name="RootNode"))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    if asset.keeps_nodes:
        built.root = _node_tree(root_obj, asset, catalog, depsgraph, built, top=True)
        return built
    stored = root_obj.get("mt2_trs")
    if stored:
        built.root.translation = tuple(stored[0:3])
        built.root.rotation = tuple(stored[3:7])
        built.root.scale = tuple(stored[7:10])
    origin = export_origin(root_obj)
    triangles: dict[tuple[str, str], list] = {}
    for obj in _members(root_obj):
        _collect(obj, origin @ obj.matrix_world, asset, catalog, depsgraph, built, triangles)
    built.root.lods = [_fragments(triangles)]

    return built


def export_origin(root_obj: bpy.types.Object) -> Matrix:
    bone = root_obj.parent if root_obj.parent is not None and root_obj.parent.mt2.role == "BONE" else None
    if bone is not None:
        return bone.matrix_world.inverted()
    if root_obj.get("mt2_trs"):
        return root_obj.matrix_world.inverted()

    return Matrix.Translation(-root_obj.matrix_world.translation)


def asset_root(obj: bpy.types.Object | None) -> bpy.types.Object | None:
    while obj is not None:
        if obj.mt2.is_asset:
            return obj
        obj = obj.parent

    return None


def _members(root_obj):
    yield root_obj
    for child in root_obj.children_recursive:
        yield child


def _node_tree(obj, asset, catalog, depsgraph, built, top: bool) -> Node:
    local = Matrix.Identity(4) if top else obj.matrix_local
    location, rotation, scale = local.decompose()
    node = Node(
        name="RootNode" if top else obj.get("mt2_node", obj.name),
        translation=swap_position(location),
        rotation=swap_rotation((rotation.x, rotation.y, rotation.z, rotation.w)),
        scale=swap_scale(scale),
        version=obj.get("mt2_version", "ModelV1"),
    )
    stored = obj.get("mt2_trs") if top else None
    if stored:
        node.translation, node.rotation, node.scale = tuple(stored[0:3]), tuple(stored[3:7]), tuple(stored[7:10])
    triangles: dict[tuple[str, str], list] = {}
    _collect(obj, Matrix.Identity(4), asset, catalog, depsgraph, built, triangles)
    for child in obj.children:
        if child.mt2.role == "NONE":
            node.children.append(_node_tree(child, asset, catalog, depsgraph, built, top=False))
        else:
            _collect(child, child.matrix_local, asset, catalog, depsgraph, built, triangles)
    node.lods = [_fragments(triangles)]

    return node


def _collect(obj, matrix, asset, catalog, depsgraph, built, triangles):
    role = obj.mt2.role
    if role in SKIPPED_ROLES or obj.type not in GEOMETRY_TYPES:
        return
    if role == "OBSTRUCTION":
        built.obstruction += _polygons(obj, matrix, depsgraph)
        return
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        _read_triangles(obj, mesh, matrix, asset, catalog, built, triangles)
    finally:
        evaluated.to_mesh_clear()


def _read_triangles(obj, mesh, matrix, asset, catalog, built, triangles):
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    if count == 0:
        return
    loops = np.empty(count * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    slots = np.empty(count, dtype=np.int32)
    mesh.loop_triangles.foreach_get("material_index", slots)
    corner_vertex = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", corner_vertex)
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    normals = np.empty(len(mesh.loops) * 3, dtype=np.float32)
    mesh.corner_normals.foreach_get("vector", normals)
    normals = normals.reshape(-1, 3)
    m = np.array(matrix, dtype=np.float64)
    positions = co @ m[:3, :3].T + m[:3, 3]
    normal_matrix = np.linalg.inv(m[:3, :3]).T
    raw_lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    original = _original_normals(mesh, co, corner_vertex)
    if original is not None:
        keep = original[1] | (np.abs(raw_lengths[:, 0] - 1.0) >= 0.01)
        normals[keep] = original[0][keep]
        raw_lengths[keep] = 1.0
    normals = normals @ normal_matrix.T
    scaled = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.where(scaled == 0, 1, scaled)
    lengths = raw_lengths
    colors = _corner_colors(mesh, corner_vertex)
    uvs = _corner_uvs(mesh)
    reverse = np.linalg.det(m[:3, :3]) > 0
    span = float(np.ptp(positions, axis=0).max()) if len(positions) else 0.0
    degenerate = DEGENERATE_RATIO * span * span
    role_material = ROLE_MATERIAL.get(obj.mt2.role)
    light_color = linear_to_srgb(obj.color) if role_material == "light" else None
    for t in range(count):
        corners = loops[3 * t:3 * t + 3]
        if reverse:
            corners = corners[[0, 2, 1]]
        a, b, c = (positions[corner_vertex[k]] for k in corners)
        face_normal = np.cross(b - a, c - a)
        area = np.linalg.norm(face_normal)
        if area <= degenerate:
            continue
        face_normal = face_normal / area
        material = role_material or _slot_material(obj, int(slots[t]), asset, built)
        fmt = _format_for(material, asset, catalog, obj.data)
        tri = []
        for corner in corners:
            p = positions[corner_vertex[corner]]
            n = normals[corner] if abs(lengths[corner, 0] - 1.0) < 0.01 else face_normal
            value = list(swap_position(p))
            if "C" in fmt:
                value += list(light_color if light_color else colors[corner])
            if "N" in fmt:
                value += list(swap_position(n))
            if "T" in fmt:
                value += list(uvs[corner])
            tri.append(tuple(float(x) for x in value))
        triangles.setdefault((material, fmt), []).append(tri)


def _original_normals(mesh, co, corner_vertex):
    stored = mesh.attributes.get(ORIGINAL_NORMALS)
    if stored is None or stored.domain != "CORNER" or stored.data_type != "FLOAT_VECTOR":
        return None
    normals = np.empty(len(mesh.loops) * 3, dtype=np.float32)
    stored.data.foreach_get("vector", normals)
    untouched = np.zeros(len(mesh.loops), dtype=bool)
    kept = mesh.attributes.get(ORIGINAL_POSITIONS)
    if kept is not None and kept.domain == "POINT" and mesh.has_custom_normals:
        positions = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        kept.data.foreach_get("vector", positions)
        span = float(np.ptp(co, axis=0).max()) if len(co) else 0.0
        still = np.abs(positions.reshape(-1, 3) - co).max(axis=1) <= 1e-6 * max(span, 1e-6)
        smooth = np.empty(len(mesh.polygons), dtype=bool)
        mesh.polygons.foreach_get("use_smooth", smooth)
        totals = np.empty(len(mesh.polygons), dtype=np.int32)
        mesh.polygons.foreach_get("loop_total", totals)
        untouched = still[corner_vertex] & np.repeat(smooth, totals)

    return normals.reshape(-1, 3), untouched


def _corner_colors(mesh, corner_vertex):
    attribute = mesh.color_attributes.active_color or (mesh.color_attributes[0] if mesh.color_attributes else None)
    if attribute is None:
        return np.ones((len(mesh.loops), 4), dtype=np.float32)
    values = np.empty(len(attribute.data) * 4, dtype=np.float32)
    attribute.data.foreach_get("color_srgb", values)
    values = values.reshape(-1, 4)

    return values if attribute.domain == "CORNER" else values[corner_vertex]


def _corner_uvs(mesh):
    layer = mesh.uv_layers.active
    if layer is None:
        return np.zeros((len(mesh.loops), 2), dtype=np.float32)
    values = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    layer.data.foreach_get("uv", values)

    return values.reshape(-1, 2)


def _slot_material(obj, slot: int, asset: AssetType, built: Built) -> str:
    material = obj.material_slots[slot].material if slot < len(obj.material_slots) else None
    if material is None:
        name = DEFAULT_MATERIAL.get(asset.coloring, "Material_tint")
        note = ("info", f"'{obj.name}' has faces without a material; exported as '{name}'", obj.name)
        if note not in built.notes:
            built.notes.append(note)

        return name

    return material.mt2.game_name or re.sub(r"\.\d{3}$", "", material.name)


def _format_for(material: str, asset: AssetType, catalog, source) -> str:
    if material == "light":
        return "PCN"
    if material in ("collision", "navmesh", "obstruction"):
        return "PNT"
    formats = source.get("mt2_formats") if asset.keeps_nodes and source is not None else None
    recorded = formats.get(material) if formats else None
    if recorded:
        return recorded
    info = catalog.get(material) if catalog else None
    if info is not None and info.kind in ("costume", "dungeon"):
        return "PNT"

    return make_format(True, True, bool(info and info.textured))


def _fragments(triangles: dict) -> list[Fragment]:
    fragments = []
    for (material, fmt), tris in triangles.items():
        fragment = Fragment(material, fmt)
        index_of: dict = {}
        for tri in tris:
            new = sum(1 for v in tri if v not in index_of)
            if len(fragment.vertices) + new > MAX_VERTICES:
                fragments.append(fragment)
                fragment = Fragment(material, fmt)
                index_of = {}
            for v in tri:
                if v not in index_of:
                    index_of[v] = len(fragment.vertices)
                    fragment.vertices.append(v)
                fragment.indices.append(index_of[v])
        fragments.append(fragment)

    return fragments


def _polygons(obj, matrix, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        polygons = []
        for face in mesh.polygons:
            points = [matrix @ mesh.vertices[i].co for i in face.vertices]
            polygons.append([swap_ground((p.x, p.y)) for p in reversed(points)])
    finally:
        evaluated.to_mesh_clear()

    return polygons
