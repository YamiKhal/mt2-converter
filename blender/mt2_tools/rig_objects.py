import bpy
from mathutils import Matrix, Quaternion, Vector

from . import game, project
from .anim_objects import NAME_KEY, channelbag, import_animations, is_keyed, owned_actions, show_rest_pose
from .costume_objects import ACTOR_KEY, bone_objects, rest_matrix, set_rest
from .mt2model.animations import Animation, read_animations
from .mt2model.axes import swap_position, swap_rotation, swap_scale
from .mt2model.gamedata import GameData
from .mt2model.model import Node
from .mt2model.naming import clean_word, prefixed
from .mt2model.rigs import merge_animations

BONE_SIZE = 0.05
MOVE_TOLERANCE = 1e-4


def game_rigs(data: GameData) -> set[str]:
    names = data.sources[-1].names()

    return {n[len("skeletons/"):-len(".vmb")] for n in names if n.startswith("skeletons/") and n.endswith(".vmb")}


def rig_name(costume: bpy.types.Object, mod_id: str, rigs: set[str]) -> str:
    typed = clean_word(costume.mt2.rig)
    if not typed:
        return costume.get(ACTOR_KEY, "humanoid")
    if typed in rigs:
        return typed

    return prefixed(mod_id, typed)


def rig_animations(rig: str) -> list[Animation]:
    rel = f"skeletons/{rig}.van"
    vanilla = game.game_data().sources[-1]
    base = read_animations(vanilla.read(rel)) if vanilla.exists(rel) else []
    own = project.read_text(game.project_dir(), rel)

    return merge_animations(base, read_animations(own) if own else [])


def starting_animations(costume: bpy.types.Object, rig: str) -> list[Animation]:
    own = project.read_text(game.project_dir(), f"skeletons/{rig}.van")
    if own:
        return read_animations(own)

    return rig_animations(costume.get(ACTOR_KEY, "humanoid")) or rig_animations("humanoid")


def skeleton_root(costume: bpy.types.Object) -> bpy.types.Object | None:
    return next((c for c in costume.children if c.mt2.role == "BONE"), None)


def bone_names(costume: bpy.types.Object) -> list[str]:
    return [o.get("mt2_node", o.name) for o in costume.children_recursive if o.mt2.role == "BONE"]


def skeleton_node(bone: bpy.types.Object) -> Node:
    location, rotation, scale = rest_matrix(bone).decompose()
    node = Node(
        name=bone.get("mt2_node", bone.name),
        translation=swap_position(location),
        rotation=swap_rotation((rotation.x, rotation.y, rotation.z, rotation.w)),
        scale=swap_scale(scale),
        version=bone.get("mt2_version", "ModelV1"),
    )
    node.children = [skeleton_node(c) for c in bone.children if c.mt2.role == "BONE"]

    return node


def add_bone(parent: bpy.types.Object, name: str, location: Vector) -> bpy.types.Object:
    bone = bpy.data.objects.new(name, None)
    for collection in parent.users_collection:
        collection.objects.link(bone)
    bone.parent = parent
    bone.mt2.role = "BONE"
    bone["mt2_node"] = name
    bone.empty_display_size = BONE_SIZE
    bone.rotation_mode = "QUATERNION"
    bone.location = parent.matrix_world.inverted() @ location
    set_rest(bone, bone.matrix_basis)

    return bone


def moved_bones(costume: bpy.types.Object) -> list[bpy.types.Object]:
    return [b for b in bone_objects(costume).values() if not is_keyed(b) and _differs(rest_matrix(b), b.matrix_basis)]


def _differs(a: Matrix, b: Matrix) -> bool:
    return any(abs(x - y) > MOVE_TOLERANCE for row_a, row_b in zip(a, b) for x, y in zip(row_a, row_b))


def keep_rest_pose(costume: bpy.types.Object, animations: list[Animation]) -> list[str]:
    moves = [(bone, rest_matrix(bone), bone.matrix_basis.copy()) for bone in moved_bones(costume)]
    if not moves:
        return []
    loaded = {a.get(NAME_KEY) for a in owned_actions(costume)}
    import_animations(costume, [a for a in animations if a.name not in loaded])
    for bone, old, new in moves:
        for action in owned_actions(costume):
            _shift_keys(action, bone, old, new)
        set_rest(bone, new)
    show_rest_pose(costume)

    return [bone.get("mt2_node", bone.name) for bone, _, _ in moves]


def _shift_keys(action: bpy.types.Action, bone: bpy.types.Object, old: Matrix, new: Matrix):
    slot = next((s for s in action.slots if s.name_display == bone.name), None)
    bag = channelbag(action, slot) if slot is not None else None
    if bag is None:
        return
    old_location, old_rotation, old_scale = old.decompose()
    new_location, new_rotation, new_scale = new.decompose()
    turn = old_rotation.inverted() @ new_rotation
    _remap(bag, "location", old_location, lambda v: list(Vector(v) + new_location - old_location))
    _remap(bag, "rotation_quaternion", old_rotation, lambda v: list(Quaternion(v) @ turn))
    _remap(bag, "scale", old_scale, lambda v: [a * n / o if o else a for a, n, o in zip(v, new_scale, old_scale)])


def _remap(bag, path: str, rest, change):
    curves = {c.array_index: c for c in bag.fcurves if c.data_path == path}
    frames = sorted({p.co[0] for c in curves.values() for p in c.keyframe_points})
    values = {f: change([curves[i].evaluate(f) if i in curves else rest[i] for i in range(len(rest))]) for f in frames}
    for index, curve in curves.items():
        for frame, value in values.items():
            curve.keyframe_points.insert(frame, value[index], options={"REPLACE", "FAST"})
        curve.update()
