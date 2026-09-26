import bpy

from . import game, project
from .anim_objects import export_animation, is_changed, owned_actions
from .costume_objects import ACTOR_KEY, TEMPLATE_KEY
from .creature_spot import spot_of, spot_placement
from .mt2model import model
from .mt2model.animations import read_animations, write_animations
from .mt2model.costume import GREY_PALETTE, read_defaults
from .mt2model.costume_files import read_costume, rename_bones
from .mt2model.naming import clean_word, prefixed
from .mt2model.rigs import (CREATURE_FOLDERS, STANDARD_BONES, creature_costume, creature_type, merge_animations,
                            missing_animations)
from .mt2model.validate import Finding
from .mt2model.variants import Creature, read_creature, set_creature
from .rig_objects import (bone_names, bone_renames, game_rigs, moved_bones, renamed_from, rig_name, skeleton_node,
                          skeleton_root, starting_animations)

CREATURE_ANIMATIONS = ("idle", "run", "death")
COLOR_TOLERANCE = 1.0 / 255


def plan_rig(result, target) -> str:
    data = game.game_data()
    costume = result.root_obj
    rigs = game_rigs(data)
    source = costume.get(ACTOR_KEY, "humanoid")
    rig = rig_name(costume, target.mod_id, rigs)
    names = bone_names(costume)
    for name in sorted({n for n in names if names.count(n) > 1}):
        result.findings.append(Finding("error", f"two bones are called '{name}'"))
    if rig in rigs:
        _plan_game_rig(result, rig, source)
    else:
        _plan_own_rig(result, target, rig, source)

    return rig


def _plan_game_rig(result, rig: str, source: str):
    data = game.game_data()
    costume = result.root_obj
    if rig != source:
        result.findings.append(Finding("error", f"a costume keeps its rig; import a {rig} costume to use the {rig} rig"))
        return
    if bone_renames(costume):
        result.findings.append(Finding("error", f"the game's {rig} rig keeps its bone names; rename them back, or "
                                                 f"give the costume its own Rig name"))
        return
    for bone in moved_bones(costume):
        result.findings.append(Finding("warning", f"the bone '{bone.name}' was moved, which the game rig can't store; "
                                                  f"move its parts instead, or give the costume its own Rig name",
                                       bone.name))
    vanilla = {n.name for n, _ in model.read_model(data.sources[-1].read(f"skeletons/{rig}.vmb")).walk()}
    added = [n for n in bone_names(costume) if n not in vanilla]
    if added:
        result.files[f"skeletons/{rig}.vmb"] = model.write_model(skeleton_node(skeleton_root(costume)))
        result.findings.append(Finding("warning", f"{', '.join(added)} will be added to every {rig} in the game, and only "
                                                  f"one mod can change a rig. Give the costume its own Rig name to "
                                                  f"keep them to this costume"))
    changed = [a for a in (export_animation(costume, a) for a in owned_actions(costume) if is_changed(a)) if a.timelines]
    if changed:
        own = project.read_text(game.project_dir(), f"skeletons/{rig}.van")
        result.texts[f"skeletons/{rig}.van"] = write_animations(merge_animations(read_animations(own), changed))


def _plan_own_rig(result, target, rig: str, source: str):
    costume = result.root_obj
    if skeleton_root(costume) is None:
        result.findings.append(Finding("error", "the costume has no skeleton; import a costume to start from"))
        return
    for bone in moved_bones(costume):
        result.findings.append(Finding("warning", f"the bone '{bone.name}' was moved; use Set rest pose in Helpers "
                                                  f"to keep it there", bone.name))
    result.files[f"skeletons/{rig}.vmb"] = model.write_model(skeleton_node(skeleton_root(costume)))
    changed = [a for a in (export_animation(costume, a) for a in owned_actions(costume) if is_changed(a)) if a.timelines]
    animations = merge_animations(starting_animations(costume, rig), changed)
    result.texts[f"skeletons/{rig}.van"] = write_animations(animations)
    needed = CREATURE_ANIMATIONS if costume.mt2.creature_type != "none" else ("idle",)
    for name in missing_animations({a.name for a in animations}, needed):
        result.findings.append(Finding("warning", f"the rig has no '{name}' animation; add one under Animation"))
    if "torso" not in bone_names(costume) and is_mount(costume):
        result.findings.append(Finding("error", "mounts need a 'torso' bone; heroes ride on it"))
    _check_renames(result, costume)
    _other_costumes(result, target, rig)


def _check_renames(result, costume: bpy.types.Object):
    for bone in [o for o in costume.children_recursive if o.mt2.role == "BONE"]:
        name = bone.get("mt2_node", bone.name)
        standard = [old for old in renamed_from(bone) if old in STANDARD_BONES]
        if standard and name not in STANDARD_BONES:
            result.findings.append(Finding("warning", f"'{name}' was '{standard[0]}'; the costume editor only restyles "
                                                      f"parts on its 8 bone names", bone.name))


def _other_costumes(result, target, rig: str):
    costume = result.root_obj
    names = set(bone_names(costume))
    renames = bone_renames(costume)
    folder = game.project_dir()
    for path in sorted((folder / "costumes").glob("*.costume")) if folder and (folder / "costumes").is_dir() else ():
        rel = f"costumes/{path.name}"
        text = path.read_text(encoding="utf-8")
        try:
            other = read_costume(text)
        except ValueError:
            continue
        if rel == result.rel or other.actor != rig:
            continue
        if any(p.bone in renames for p in other.parts):
            result.texts[rel] = rename_bones(text, renames)
        missing = sorted({p.bone for p in other.parts if p.model_file and renames.get(p.bone, p.bone) not in names})
        if missing:
            result.findings.append(Finding("warning", f"{path.stem} puts parts on {', '.join(missing)}, which the "
                                                      f"rig won't have any more"))
    rigs = game_rigs(game.game_data())
    for other in bpy.data.objects:
        if other is costume or not (other.mt2.is_asset and other.mt2.asset == "costume"):
            continue
        if rig_name(other, target.mod_id, rigs) == rig and set(bone_names(other)) != names:
            result.findings.append(Finding("warning", f"'{other.name}' in this file uses the same rig with other "
                                                      f"bones; exporting it would change the rig back", other.name))


def needs_own_parts(costume: bpy.types.Object) -> bool:
    return is_mount(costume) and _colors_changed(costume)


def _colors_changed(costume: bpy.types.Object) -> bool:
    data = game.game_data()
    defaults = costume.get(TEMPLATE_KEY, "")[: -len(".costume")] + ".defaults"
    source = read_defaults(data.read(defaults)) if data.exists(defaults) else GREY_PALETTE
    colors = [tuple(c.color) for c in costume.mt2.palette]

    return any(abs(a - b) > COLOR_TOLERANCE for new, old in zip(colors, source) for a, b in zip(new, old))


def is_mount(costume: bpy.types.Object) -> bool:
    data = game.game_data()
    template = costume.get(TEMPLATE_KEY)

    return bool(template) and data.exists(template) and b"saddle" in data.read(template)


def plan_creature_type(result, target, stem: str, rig: str):
    kind = result.root_obj.mt2.creature_type
    if kind == "none":
        return
    data = game.game_data()
    folder = CREATURE_FOLDERS[kind]
    template = _creature_template(folder, result.root_obj.get(ACTOR_KEY, "humanoid"))
    if template is None:
        result.findings.append(Finding("error", f"no creature in {folder} to start from"))
        return
    name = result.root_obj.mt2.display_name or stem
    result.texts[f"{folder}/{stem}.vrt"] = creature_type(data.read(template), name, stem)
    if kind == "class" and rig != "humanoid":
        result.findings.append(Finding("warning", "heroes can only hold weapons on the humanoid rig"))


def _creature_template(folder: str, actor: str) -> str | None:
    data = game.game_data()
    vanilla = data.sources[-1]
    prefabs = sorted(n for n in vanilla.names() if n.startswith(folder + "/") and n.endswith(".vrt"))
    for rel in prefabs:
        costume = f"costumes/{creature_costume(vanilla.read(rel))}.costume"
        if vanilla.exists(costume) and read_costume(vanilla.read(costume)).actor == actor:
            return rel

    return prefabs[0] if prefabs else None


def plan_flight_creature(result, target, variant_text: str) -> str:
    root = result.root_obj
    current = read_creature(variant_text)
    typed = clean_word(root.mt2.creature)
    spot = spot_of(root)
    if current is None and not typed:
        return variant_text
    costume = _costume_name(target.mod_id, typed) if typed else current.costume
    offset, rotation = spot_placement(root, spot) if spot else (None, None)
    if typed and not _costume_exists(costume):
        result.findings.append(Finding("warning", f"there's no costume '{costume}' yet; export it too"))

    return set_creature(variant_text, Creature(costume, root.mt2.creature_animation or "idle", offset, rotation))


def _costume_name(mod_id: str, typed: str) -> str:
    data = game.game_data()

    return typed if data.exists(f"costumes/{typed}.costume") else prefixed(mod_id, typed)


def _costume_exists(costume: str) -> bool:
    if game.game_data().exists(f"costumes/{costume}.costume"):
        return True
    mod_id = bpy.context.scene.mt2.mod_id

    return any(o.mt2.is_asset and o.mt2.asset == "costume" and prefixed(mod_id, o.mt2.name or o.name) == costume
               for o in bpy.data.objects)
