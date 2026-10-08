import bpy

from .. import game, mod_folder
from ..mt2model import model, records
from ..mt2model.animations import DOOR_SEQUENCE, Animation, pose_jumps, read_animations, write_animations
from ..mt2model.rigs import GIZMO_ANIMATIONS, merge_animations, mod_animations
from ..mt2model.validate import Finding
from ..objects.animation import export_animation, is_changed, owned_actions, unmatched_slots
from ..objects.costumes import MESH_HASH_KEY, mesh_hash
from ..objects.rigs import game_animations

JUMP_TOLERANCE = 0.005


def is_game_gizmo(root: bpy.types.Object) -> bool:
    data = game.game_data()
    variant = root.mt2.source_variant

    return root.mt2.asset == "gizmo" and bool(variant) and data is not None and data.sources[-1].exists(variant)


def edits_game_gizmo(root: bpy.types.Object) -> bool:
    return root.mt2.edit_game and is_game_gizmo(root)


def game_animation_file(root: bpy.types.Object) -> str | None:
    vanilla = game.game_data().sources[-1]
    owner = next(iter(records.parse(vanilla.read(root.mt2.source_variant))), None)
    animation_file = owner.prop("animationFile") if owner else None

    return animation_file or None


def plan_game_gizmo(result):
    root = result.root_obj
    animation_file = game_animation_file(root)
    if animation_file is None:
        result.findings.append(Finding("error", "this gizmo has no animations in the game to change"))
        return
    result.rel = f"{animation_file}.van"
    actions = [a for a in owned_actions(root) if is_changed(a)]
    changed = [a for a in (export_animation(root, action) for action in actions) if a.timelines]
    if not changed:
        result.findings.append(Finding("error", f"no animation is changed yet; change {', '.join(GIZMO_ANIMATIONS)}"))
        return
    for animation in changed:
        if animation.name not in GIZMO_ANIMATIONS:
            result.findings.append(
                Finding(
                    "warning",
                    f"the game never plays '{animation.name}'; gizmos only play {', '.join(GIZMO_ANIMATIONS)}",
                )
            )
    _check_nodes(result, animation_file, changed, actions)
    if _model_changed(root):
        result.findings.append(
            Finding(
                "warning",
                "changes to the model itself aren't exported here; disable "
                "Change the game's to make a new gizmo with them",
            )
        )
    check_sequence(result, merge_animations(game_animations(result.rel), changed), game_reference(result.rel))
    own = mod_folder.read_text(game.project_dir(), result.rel)
    animations = mod_animations(
        game_reference(result.rel), read_animations(own) if own else [], changed, root.mt2.standalone
    )
    result.texts[result.rel] = write_animations(animations)


def game_reference(rel: str) -> list[Animation]:
    vanilla = game.game_data().sources[-1]

    return read_animations(vanilla.read(rel)) if vanilla.exists(rel) else []


def check_sequence(result, animations: list[Animation], reference: list[Animation]):
    by_name = {a.name: a for a in animations}
    usual = {a.name: a for a in reference}
    warned = set()
    for first, then in DOOR_SEQUENCE:
        if first not in by_name or then not in by_name:
            continue
        game_jumps = pose_jumps(usual[first], usual[then]) if first in usual and then in usual else {}
        for node, gaps in pose_jumps(by_name[first], by_name[then]).items():
            normal = game_jumps.get(node, (0.0, 0.0, 0.0))
            if (node, first, then) in warned or (node, then, first) in warned:
                continue
            if any(gap > JUMP_TOLERANCE >= known for gap, known in zip(gaps, normal)):
                warned.add((node, first, then))
                result.findings.append(
                    Finding(
                        "warning",
                        f"'{node}' jumps from the end of {first} to the start of "
                        f"{then}; key it in {then} where {first} leaves it",
                    )
                )


def _check_nodes(result, animation_file: str, changed: list, actions: list):
    vanilla = game.game_data().sources[-1]
    model_rel = f"{animation_file}.vmb"
    known = (
        {n.name for n, _ in model.read_model(vanilla.read(model_rel)).walk()} if vanilla.exists(model_rel) else set()
    )
    unknown = sorted({t.node for a in changed for t in a.timelines if t.node not in known} if known else set())
    unknown += sorted({name for action in actions for name in unmatched_slots(result.root_obj, action)})
    if unknown:
        result.findings.append(
            Finding("warning", f"the game's model has no {', '.join(unknown)}, so those keys do nothing")
        )


def _model_changed(root: bpy.types.Object) -> bool:
    meshes = [o for o in [root, *root.children_recursive] if o.type == "MESH" and o.mt2.role == "NONE"]

    return any(o.get(MESH_HASH_KEY) != mesh_hash(o) for o in meshes)
