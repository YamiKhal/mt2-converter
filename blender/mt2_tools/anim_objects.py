import hashlib

import bpy

from .costume_objects import REST_KEY, rest_matrix
from .mt2model.animations import FPS, Animation, Timeline
from .mt2model.axes import swap_position, swap_rotation, swap_scale

OWNER_KEY = "mt2_owner"
NAME_KEY = "mt2_name"
PLAYBACK_KEY = "mt2_playback"
HASH_KEY = "mt2_hash"
FIRST_FRAME = 1
REST_POSE = "MT2_REST_POSE"
FRAME_MARGIN = 1e-3

CHANNEL_PATHS = (("location", 3), ("rotation_quaternion", 4), ("scale", 3))


def node_objects(root: bpy.types.Object) -> dict[str, bpy.types.Object]:
    role = "BONE" if root.mt2.asset == "costume" else "NONE"
    nodes = {}
    for obj in [root, *root.children_recursive]:
        name = obj.get("mt2_node")
        if name and name not in nodes and obj.mt2.role == role:
            nodes[name] = obj

    return nodes


def import_animations(root: bpy.types.Object, animations: list[Animation]) -> list[bpy.types.Action]:
    nodes = node_objects(root)
    actions = [_make_action(root, animation, nodes) for animation in animations]
    if actions:
        assign(root, actions[0])

    return actions


def _make_action(root: bpy.types.Object, animation: Animation, nodes) -> bpy.types.Action:
    action = bpy.data.actions.new(animation.name)
    action[OWNER_KEY] = root
    action[NAME_KEY] = animation.name
    action[PLAYBACK_KEY] = animation.playback
    action.use_fake_user = True
    strip = action.layers.new("Layer").strips.new(type="KEYFRAME")
    for timeline in animation.timelines:
        obj = nodes.get(timeline.node)
        if obj is None:
            continue
        slot = action.slots.new(id_type="OBJECT", name=obj.name)
        bag = strip.channelbag(slot, ensure=True)
        _add_curves(bag, "location", [(t, swap_position(v)) for t, v in timeline.translation])
        _add_curves(bag, "rotation_quaternion", [(t, _blender_quaternion(v)) for t, v in timeline.rotation])
        _add_curves(bag, "scale", [(t, swap_scale(v)) for t, v in timeline.scale])
    action[HASH_KEY] = action_hash(action)

    return action


def _blender_quaternion(values) -> tuple[float, ...]:
    x, y, z, w = swap_rotation(values)

    return (w, x, y, z)


def _add_curves(bag, path: str, keys):
    if not keys:
        return
    for index in range(len(keys[0][1])):
        curve = bag.fcurves.new(path, index=index)
        curve.keyframe_points.add(len(keys))
        coordinates = [c for time, values in keys for c in (FIRST_FRAME + time * FPS, values[index])]
        curve.keyframe_points.foreach_set("co", coordinates)
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
        curve.update()


def owned_actions(root: bpy.types.Object) -> list[bpy.types.Action]:
    return [a for a in bpy.data.actions if a.get(OWNER_KEY) == root]


def assign(root: bpy.types.Object, action: bpy.types.Action):
    for obj in node_objects(root).values():
        if REST_KEY in obj:
            obj.matrix_basis = rest_matrix(obj)
        slot = next((s for s in action.slots if s.name_display == obj.name), None)
        if slot is None:
            slot = action.slots.new(id_type="OBJECT", name=obj.name)
        if obj.animation_data is None:
            obj.animation_data_create()
        if obj.rotation_mode != "QUATERNION":
            obj.rotation_mode = "QUATERNION"
        obj.animation_data.action = action
        obj.animation_data.action_slot = slot
    start, end = action.frame_range
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = int(start), max(int(end), int(start) + 1)


def show_rest_pose(root: bpy.types.Object):
    for obj in node_objects(root).values():
        if obj.animation_data is not None:
            obj.animation_data.action = None
        if REST_KEY in obj:
            obj.matrix_basis = rest_matrix(obj)


def is_keyed(obj: bpy.types.Object) -> bool:
    data = obj.animation_data
    if data is None or data.action is None or data.action_slot is None:
        return False
    bag = channelbag(data.action, data.action_slot)

    return bag is not None and len(bag.fcurves) > 0


def channelbag(action: bpy.types.Action, slot):
    strip = action.layers[0].strips[0] if action.layers and action.layers[0].strips else None

    return strip.channelbag(slot) if strip else None


def new_action(root: bpy.types.Object, name: str) -> bpy.types.Action:
    action = bpy.data.actions.new(name)
    action[OWNER_KEY] = root
    action[NAME_KEY] = name
    action[PLAYBACK_KEY] = "Once"
    action.use_fake_user = True
    action.layers.new("Layer").strips.new(type="KEYFRAME")
    assign(root, action)

    return action


def export_animation(root: bpy.types.Object, action: bpy.types.Action) -> Animation:
    nodes = {obj.name: name for name, obj in node_objects(root).items()}
    animation = Animation(action.get(NAME_KEY, action.name), action.get(PLAYBACK_KEY, "Once"))
    first, last = action.frame_range
    start = int(round(first))
    for slot in action.slots:
        bag = channelbag(action, slot)
        node = nodes.get(slot.name_display)
        if bag is None or node is None or not len(bag.fcurves):
            continue
        location, rotation, scale = rest_matrix(bpy.data.objects[slot.name_display]).decompose()
        timeline = Timeline(node)
        for frame in _frames(bag, first, last):
            time = (frame - start) / FPS
            w, x, y, z = _sample(bag, "rotation_quaternion", frame, rotation)
            timeline.translation.append((time, tuple(swap_position(_sample(bag, "location", frame, location)))))
            timeline.rotation.append((time, tuple(swap_rotation((x, y, z, w)))))
            timeline.scale.append((time, tuple(swap_scale(_sample(bag, "scale", frame, scale)))))
        animation.timelines.append(timeline)

    return animation


def _frames(bag, first: float, last: float) -> list[float]:
    points = [p for curve in bag.fcurves for p in curve.keyframe_points]
    if points and all(p.interpolation == "LINEAR" for p in points):
        frames = {round(p.co[0], 4) for p in points if first - FRAME_MARGIN <= p.co[0] <= last + FRAME_MARGIN}
        return sorted(frames)

    return list(range(int(round(first)), int(round(last)) + 1))


def _sample(bag, path: str, frame: float, rest) -> list[float]:
    values = list(rest)
    for curve in bag.fcurves:
        if curve.data_path == path and curve.array_index < len(values):
            values[curve.array_index] = curve.evaluate(frame)

    return values


def action_hash(action: bpy.types.Action) -> str:
    digest = hashlib.sha1()
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    digest.update(f"{curve.data_path}{curve.array_index}".encode())
                    digest.update(",".join(f"{p.co[0]:.4f}:{p.co[1]:.5f}" for p in curve.keyframe_points).encode())
    digest.update(str(action.get(PLAYBACK_KEY)).encode())

    return digest.hexdigest()


def is_changed(action: bpy.types.Action) -> bool:
    return action.get(HASH_KEY) != action_hash(action)
