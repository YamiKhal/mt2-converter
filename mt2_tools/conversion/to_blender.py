import bpy

from ..materials.game_materials import material_for
from ..mt2model.assets import SPECIAL_MATERIALS
from ..mt2model.axes import AXES_VERSION, swap_position, swap_rotation, swap_scale
from ..mt2model.colors import srgb_to_linear
from ..mt2model.formats import layout
from ..mt2model.materials import MaterialCatalog
from ..mt2model.model import Fragment, Node

ROLE_OF = {"light": "LIGHT", "obstruction": "OBSTRUCTION", "collision": "COLLISION", "navmesh": "NAVMESH"}
ORIGINAL_NORMALS = "mt2_normal"
ORIGINAL_POSITIONS = "mt2_position"


def import_model(root: Node, name: str, catalog: MaterialCatalog | None, collection) -> bpy.types.Object:
    obj = _import_node(root, name, catalog, collection, None)
    obj["mt2_trs"] = [*root.translation, *root.rotation, *root.scale]
    obj["mt2_axes"] = AXES_VERSION

    return obj


def _import_node(node: Node, fallback_name: str, catalog, collection, parent) -> bpy.types.Object:
    name = fallback_name if node.name in ("RootNode", "<dummy_root>", "") else node.name
    render = [f for f in node.fragments if f.material not in SPECIAL_MATERIALS]
    data = build_mesh(name, render, catalog) if render else None
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.parent = parent
    obj.location = swap_position(node.translation)
    obj.rotation_mode = "QUATERNION"
    q = swap_rotation(node.rotation)
    obj.rotation_quaternion = (q[3], q[0], q[1], q[2])
    obj.scale = swap_scale(node.scale)
    obj["mt2_node"] = node.name
    obj["mt2_version"] = node.version
    if data is None:
        obj.empty_display_size = 0.5
    for fragment in node.fragments:
        if fragment.material in SPECIAL_MATERIALS:
            _import_special(fragment, name, catalog, collection, obj)
    for child in node.children:
        _import_node(child, child.name, catalog, collection, obj)

    return obj


def _import_special(fragment: Fragment, owner: str, catalog, collection, parent):
    obj = bpy.data.objects.new(
        f"{owner} {fragment.material}", build_mesh(f"{owner} {fragment.material}", [fragment], catalog)
    )
    collection.objects.link(obj)
    obj.parent = parent
    obj.mt2.role = ROLE_OF[fragment.material]
    obj.display_type = "WIRE"
    obj.hide_render = True
    color_at = layout(fragment.format).color
    if fragment.material == "light" and color_at is not None and fragment.vertices:
        obj.color = srgb_to_linear(fragment.vertices[0][color_at : color_at + 4])


def build_mesh(name: str, fragments: list[Fragment], catalog: MaterialCatalog | None) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    positions, faces, face_materials = [], [], []
    colors, normals, uvs = [], [], []
    any_color = any(layout(f.format).color is not None for f in fragments)
    any_uv = any(layout(f.format).texel is not None for f in fragments)
    any_normal = any(layout(f.format).normal is not None for f in fragments)
    formats = {}
    for slot, fragment in enumerate(fragments):
        lay = layout(fragment.format)
        base = len(positions)
        formats[fragment.material] = fragment.format
        positions += [swap_position(v) for v in fragment.vertices]
        indices = fragment.indices
        for k in range(0, len(indices) - len(indices) % 3, 3):
            a, b, c = indices[k : k + 3]
            if len({a, b, c}) < 3:
                continue
            faces.append((base + a, base + c, base + b))
            face_materials.append(slot)
            for i in (a, c, b):
                v = fragment.vertices[i]
                colors.append(v[lay.color : lay.color + 4] if lay.color is not None else (1.0, 1.0, 1.0, 1.0))
                normals.append(
                    swap_position(v[lay.normal : lay.normal + 3]) if lay.normal is not None else (0.0, 0.0, 0.0)
                )
                uvs.append(v[lay.texel : lay.texel + 2] if lay.texel is not None else (0.0, 0.0))
    mesh.from_pydata(positions, [], faces)
    mesh.polygons.foreach_set("material_index", face_materials)
    if any_color:
        attribute = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        attribute.data.foreach_set("color_srgb", [x for c in colors for x in c])
        mesh.color_attributes.active_color = attribute
    if any_uv:
        mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", [x for uv in uvs for x in uv])
    if any_normal:
        mesh.polygons.foreach_set("use_smooth", [True] * len(faces))
        mesh.normals_split_custom_set(normals)
        stored = mesh.attributes.new(ORIGINAL_NORMALS, "FLOAT_VECTOR", "CORNER")
        stored.data.foreach_set("vector", [x for n in normals for x in n])
        kept = mesh.attributes.new(ORIGINAL_POSITIONS, "FLOAT_VECTOR", "POINT")
        kept.data.foreach_set("vector", [x for p in positions for x in p])
    for fragment in fragments:
        mesh.materials.append(material_for(fragment.material))
    mesh["mt2_formats"] = formats
    mesh.update()

    return mesh
