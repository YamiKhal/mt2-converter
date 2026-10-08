import bpy

from ..mt2model.animations import FPS, chain, door_order
from .animation import FIRST_FRAME, NAME_KEY, assign, export_animation, make_action, owned_actions

PREVIEW_KEY = "mt2_door_preview"
PREVIEW_NAME = "Door preview"
MARKER_PREFIX = "door: "
GAP = 1 / FPS


def is_door(root: bpy.types.Object) -> bool:
    names = _names(root)

    return root.mt2.asset == "gizmo" and "open" in names and ("unlock" in names or "close" in names)


def play_door(root: bpy.types.Object) -> bpy.types.Action:
    clear_door_preview(root)
    by_name = {a.get(NAME_KEY, a.name): a for a in owned_actions(root)}
    order = door_order(by_name)
    played = [export_animation(root, by_name[name]) for name in order]
    chained, starts = chain(PREVIEW_NAME, played, GAP)
    action = make_action(root, chained)
    action[PREVIEW_KEY] = root
    assign(root, action)
    scene = bpy.context.scene
    for name, start in zip(order, starts):
        scene.timeline_markers.new(MARKER_PREFIX + name, frame=int(round(FIRST_FRAME + start * FPS)))
    scene.frame_set(scene.frame_start)

    return action


def door_preview_action(root: bpy.types.Object) -> bpy.types.Action | None:
    return next((a for a in bpy.data.actions if a.get(PREVIEW_KEY) == root), None)


def clear_door_preview(root: bpy.types.Object):
    for action in [a for a in bpy.data.actions if a.get(PREVIEW_KEY) == root]:
        bpy.data.actions.remove(action)
    markers = bpy.context.scene.timeline_markers
    for marker in [m for m in markers if m.name.startswith(MARKER_PREFIX)]:
        markers.remove(marker)


def _names(root: bpy.types.Object) -> set[str]:
    return {a.get(NAME_KEY, a.name) for a in owned_actions(root)}
