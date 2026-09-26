import hashlib

import bpy
import numpy as np
from mathutils import Matrix

from . import convert_in, game, shading
from .mt2model import model
from .mt2model.axes import AXES_VERSION, swap_position, swap_scale
from .mt2model.costume import GREY_PALETTE, read_defaults
from .mt2model.costume_files import PartPlacement, read_costume
from .palette import show_palette

MESH_HASH_KEY = "mt2_mesh_hash"
TEMPLATE_KEY = "mt2_costume_template"
ACTOR_KEY = "mt2_actor"
REST_KEY = "mt2_rest"


def import_costume(context, costume_rel: str) -> bpy.types.Object:
    data = game.game_data()
    costume = read_costume(data.read(costume_rel))
    collection = context.collection
    stem = costume_rel.rsplit("/", 1)[-1][: -len(".costume")]
    root = bpy.data.objects.new(f"Costume {stem}", None)
    collection.objects.link(root)
    root.empty_display_type = "PLAIN_AXES"
    root.mt2.is_asset = True
    root.mt2.asset = "costume"
    root.mt2.name = stem
    root[TEMPLATE_KEY] = costume_rel
    root[ACTOR_KEY] = costume.actor
    root.mt2.rig = costume.actor
    skeleton = convert_in.import_model(model.read_model(data.read(_skeleton_path(costume.actor))),
                                       f"{stem} skeleton", game.catalog(), collection)
    skeleton.parent = root
    for obj in [skeleton, *skeleton.children_recursive]:
        obj.mt2.role = "BONE"
        obj.empty_display_size = 0.05
        set_rest(obj, obj.matrix_basis)
    bones = bone_objects(root)
    for part in costume.parts:
        if part.bone in bones:
            bones[part.bone].matrix_parent_inverse = _offset_matrix(part)
    context.view_layer.update()
    material = shading.game_material("costume", "costume").copy()
    material.name = f"costume {stem}"
    for part in costume.parts:
        if part.model_file and part.bone in bones and data.exists(part.model_file):
            _import_part(context, part, bones[part.bone], material)
    defaults = costume_rel[: -len(".costume")] + ".defaults"
    for color in read_defaults(data.read(defaults)) if data.exists(defaults) else GREY_PALETTE:
        root.mt2.palette.add().color = color
    show_palette(root)

    return root


def _skeleton_path(actor: str) -> str:
    data = game.game_data()
    for rel in (f"{actor}.vmb", f"skeletons/{actor}.vmb"):
        if data.exists(rel):
            return rel

    return "skeletons/humanoid.vmb"


def _import_part(context, part: PartPlacement, bone: bpy.types.Object, material: bpy.types.Material):
    data = game.game_data()
    obj = convert_in.import_model(model.read_model(data.read(part.model_file)), part.bone,
                                  game.catalog(), context.collection)
    del obj["mt2_trs"]
    obj["mt2_axes"] = AXES_VERSION
    obj.mt2.is_asset = True
    obj.mt2.asset = "costume_part"
    obj.mt2.bone = part.bone
    obj.mt2.source_path = part.model_file
    obj.mt2.normalise = True
    for slot in obj.material_slots:
        slot.material = material
    obj.parent = bone
    obj.matrix_world = bone.matrix_world @ Matrix.Scale(part.model_scale, 4)
    obj[MESH_HASH_KEY] = mesh_hash(obj)


def _offset_matrix(part: PartPlacement) -> Matrix:
    scale = Matrix.Diagonal((*swap_scale(part.offset_scale), 1.0))

    return Matrix.Translation(swap_position(part.offset)) @ scale


def bone_objects(root: bpy.types.Object) -> dict[str, bpy.types.Object]:
    return {o.get("mt2_node", o.name): o for o in root.children_recursive if o.mt2.role == "BONE"}


def costume_root(obj: bpy.types.Object | None) -> bpy.types.Object | None:
    while obj is not None:
        if obj.mt2.is_asset and obj.mt2.asset == "costume":
            return obj
        obj = obj.parent

    return None


def parts_of(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [o for o in root.children_recursive if o.mt2.is_asset and o.mt2.asset == "costume_part"]


def is_loose_part(obj: bpy.types.Object | None) -> bool:
    return (obj is not None and obj.type == "MESH" and not obj.mt2.is_asset and obj.mt2.role == "NONE"
            and obj.parent is not None and obj.parent.mt2.role == "BONE")


def loose_parts(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [o for o in root.children_recursive if is_loose_part(o)]


def placement(part: bpy.types.Object, model_file: str, extent: float) -> PartPlacement:
    bone = part.parent
    offset = bone.matrix_parent_inverse

    return PartPlacement(bone.get("mt2_node", bone.name), model_file, extent,
                         tuple(float(x) for x in swap_position(offset.to_translation())),
                         tuple(float(x) for x in swap_scale(offset.to_scale())))


def rest_matrix(bone: bpy.types.Object) -> Matrix:
    stored = bone.get(REST_KEY)
    if stored is None:
        return bone.matrix_basis.copy()

    return Matrix([stored[i:i + 4] for i in range(0, 16, 4)])


def set_rest(bone: bpy.types.Object, matrix: Matrix):
    bone[REST_KEY] = [x for row in matrix for x in row]


def mesh_hash(obj: bpy.types.Object) -> str:
    mesh = obj.data
    digest = hashlib.sha1()
    for name, size in (("co", 3),):
        values = np.empty(len(mesh.vertices) * size, dtype=np.float32)
        mesh.vertices.foreach_get(name, values)
        digest.update(np.round(values, 5).tobytes())
    layer = mesh.uv_layers.active
    if layer is not None:
        values = np.empty(len(mesh.loops) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", values)
        digest.update(np.round(values, 5).tobytes())

    return digest.hexdigest()


def is_unchanged(part: bpy.types.Object) -> bool:
    return bool(part.mt2.source_path) and part.get(MESH_HASH_KEY) == mesh_hash(part) and sits_on_bone(part)


def sits_on_bone(part: bpy.types.Object) -> bool:
    local = part.matrix_parent_inverse @ part.matrix_basis

    return local.to_translation().length < 1e-4 and local.to_quaternion().angle < 1e-4
