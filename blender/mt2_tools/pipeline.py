from dataclasses import dataclass, field

import bpy

from . import convert_out, game, project
from .mt2model import model, records
from .mt2model.artpacks import WEAPON_PACK_PREFIX, art_pack, is_empty, pack_content, weapon_pack, weapon_pack_path
from .mt2model.assets import asset_type
from .mt2model.axes import AXES_VERSION
from .mt2model.costume import normalise
from .mt2model.footprint import is_convex
from .mt2model.pads import pad_problems
from .anim_objects import export_animation, owned_actions
from .bridge_plan import plan_bridge
from .costume_objects import TEMPLATE_KEY, costume_root, is_unchanged, loose_parts, parts_of, placement
from .creature_spot import FLIGHT_POINTS
from .gizmo_plan import check_sequence, edits_game_gizmo, game_reference, plan_game_gizmo
from .mt2model.animations import write_animations
from .mt2model.dungeons import write_sockets
from .socket_objects import collect_sockets
from .mt2model.costume_files import write_costume, write_defaults
from .pad_objects import collect_pads, has_own_pads
from .mt2model.i18n import set_strings, strings_path
from .mt2model.naming import ExportTarget, model_path, prefixed, target_problems
from .mt2model.obstruction import obs_file_name, write_obstruction
from .mt2model.validate import Finding, has_errors, validate
from .mt2model.vehicle_tool import TOOL_FILE, vehicle_tool_file
from .mt2model.variants import building_kinds, derive_variant, display_name_key, variant_files
from .rig_objects import bone_renames
from .rig_plan import needs_own_parts, plan_creature_type, plan_flight_creature, plan_rig


@dataclass
class Plan:
    root_obj: bpy.types.Object
    rel: str = ""
    built: convert_out.Built | None = None
    findings: list[Finding] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    parts: list["Plan"] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        ready = self.built is not None or (self.texts and self.root_obj.mt2.asset in ("costume", "gizmo"))

        return bool(ready) and not has_errors(self.findings) and all(p.ok for p in self.parts)


def target_for(root_obj: bpy.types.Object) -> ExportTarget:
    s = root_obj.mt2
    mod_id = bpy.context.scene.mt2.mod_id
    costume = costume_root(root_obj.parent) if s.asset == "costume_part" else None
    costume_set = prefixed(mod_id, costume.mt2.name or costume.name) if costume else s.costume_set
    bone = root_obj.parent.get("mt2_node", root_obj.parent.name) if costume else s.bone

    return ExportTarget(
        asset=s.asset, name=s.name or root_obj.name, mod_id=mod_id,
        scenery_type=s.scenery_type, weapon_category=s.weapon_category, item_level=s.item_level,
        costume_set=costume_set, bone=bone, theme=s.theme, slot=s.slot, building_dir=s.building_dir,
        wall_piece=s.wall_piece, tag_place=s.tag_place, tag_kind=s.tag_kind, tag_small=s.tag_small,
        tag_extra=s.tag_extra.split(), raw_path=s.raw_path, vehicle_kind=s.vehicle_kind,
        gizmo_dir=s.gizmo_dir, dungeon_theme=s.dungeon_theme, bridge_piece=s.bridge_piece, tile_kind=s.tile_kind, shape=s.shape,
    )


def plan(root_obj: bpy.types.Object) -> Plan:
    result = Plan(root_obj)
    data = game.game_data()
    if data is None:
        result.findings.append(Finding("error", "set the game folder in the add-on preferences first"))
        return result
    target = target_for(root_obj)
    result.findings += [Finding("error", p) for p in target_problems(target)]
    if result.findings:
        return result
    if root_obj.get("mt2_trs") and root_obj.get("mt2_axes") != AXES_VERSION:
        result.findings.append(Finding("error", "imported with MT2 Tools 0.1.0, which mirrored models in Blender. "
                                                "Import the model again and redo the changes"))
        return result
    if edits_game_gizmo(root_obj):
        plan_game_gizmo(result)
        return result
    result.rel = model_path(target)
    other = _other_asset_at(root_obj, result.rel)
    if other is not None:
        result.findings.append(Finding("error", f"'{other.name}' in this file also exports to {result.rel}; "
                                                f"give one of them another name", other.name))
    if target.asset == "costume":
        _plan_costume(result, target)
        return result
    asset = asset_type(target.asset)
    result.built = convert_out.build(root_obj, asset, game.catalog())
    result.findings += [Finding(level, message, object_name) for level, message, object_name in result.built.notes]
    if target.asset == "costume_part" and root_obj.mt2.normalise:
        scale = normalise(result.built.root)
        root_obj.mt2.model_scale = scale
        result.findings.append(Finding("info", f"normalised; use modelScale {scale:.6f} for this part in the .costume"))
    result.findings += validate(result.built.root, asset, game.catalog(), replaces_vanilla=data.is_vanilla(result.rel))
    previous = root_obj.mt2.exported_path
    if previous and previous != result.rel and target.asset != "costume_part":
        result.findings.append(Finding("error", f"this asset was exported as {previous}. Saves find models by file name, "
                                                f"so renaming breaks it where players placed it. "
                                                f"Use 'Forget previous export' if this is meant to be a new model"))
    _plan_obstruction(result, target)
    if target.asset == "building":
        _plan_variant(result, target)
    if target.asset == "weapon":
        _plan_weapon_category(result, target)
    if target.asset == "vehicle":
        _plan_vehicle(result, target)
    if target.asset == "gizmo":
        _plan_gizmo(result, target)
    if target.asset == "dungeon_tile":
        _plan_dungeon_tile(result, target)
    if target.asset == "bridge":
        plan_bridge(result, target)

    return result


def _other_asset_at(root_obj: bpy.types.Object, rel: str) -> bpy.types.Object | None:
    for obj in bpy.data.objects:
        if obj == root_obj or not obj.mt2.is_asset:
            continue
        if obj.mt2.exported_path == rel or model_path(target_for(obj)) == rel:
            return obj

    return None


def _plan_obstruction(result: Plan, target: ExportTarget):
    polygons = result.built.obstruction
    if not polygons or target.asset == "bridge":
        return
    if target.asset not in ("scenery", "tagged"):
        result.findings.append(Finding("warning", "obstruction shapes only work for scenery; they are not exported"))
        return
    for polygon in polygons:
        if not is_convex(polygon):
            result.findings.append(Finding("error", "every obstruction face must be convex; split concave shapes into several faces"))
            return
    result.texts[f"{result.rel.rsplit('/', 1)[0]}/{obs_file_name(result.rel.rsplit('/', 1)[1])}"] = write_obstruction(polygons)


def _plan_variant(result: Plan, target: ExportTarget):
    data = game.game_data()
    template = result.root_obj.mt2.source_variant or _default_template(target.building_dir)
    if not template or not data.exists(template):
        result.findings.append(Finding("error", f"no .variant in {target.building_dir} to copy pads and entrances from"))
        return
    stem = prefixed(target.mod_id, target.name)
    pads = collect_pads(result.root_obj) if has_own_pads(result.root_obj) else None
    variant = derive_variant(data.read(template), stem, result.rel, pads)
    if target.building_dir == FLIGHT_POINTS:
        variant = plan_flight_creature(result, target, variant)
    result.texts[f"{target.building_dir}/{stem}.variant"] = variant
    if pads is not None:
        result.findings += [Finding(level, message) for level, message in pad_problems(pads)]
    display = result.root_obj.mt2.display_name
    kind = next((k for k in building_kinds(data) if k.directory == target.building_dir), None)
    if display and kind:
        rel = strings_path(target.mod_id)
        existing = _read_project_text(rel)
        result.texts[rel] = set_strings(existing, {display_name_key(kind.key, stem): display})


def _plan_dungeon_tile(result: Plan, target: ExportTarget):
    result.texts[result.rel[: -len(".vmb")] + ".vrt"] = write_sockets(collect_sockets(result.root_obj))
    materials = {f.material for node, _ in result.built.root.walk() for f in node.fragments}
    for special in ("collision", "navmesh"):
        if special not in materials:
            result.findings.append(Finding("warning", f"no {special} piece; vanilla tiles all have one"))
    if "_" in target.dungeon_theme:
        result.findings.append(Finding("warning", f"dungeons place props by their theme's name, and prop file names split "
                                                  f"at '_', so '{target.dungeon_theme}' never gets props. "
                                                  f"Make the theme again with New theme"))


def _plan_gizmo(result: Plan, target: ExportTarget):
    data = game.game_data()
    template = result.root_obj.mt2.source_variant or next(iter(variant_files(data, target.gizmo_dir)), None)
    if not template or not data.exists(template):
        result.findings.append(Finding("error", f"no gizmo .variant in {target.gizmo_dir} to start from"))
        return
    stem = prefixed(target.mod_id, target.name)
    pads = collect_pads(result.root_obj) if has_own_pads(result.root_obj) else None
    variant = derive_variant(data.read(template), stem, result.rel, pads, label="mmoGizmoVariant")
    exported = [a for a in (export_animation(result.root_obj, a) for a in owned_actions(result.root_obj)) if a.timelines]
    if exported:
        animation_rel = f"{target.gizmo_dir}/{stem}"
        parsed = records.parse(variant)
        parsed[0].set_prop("animationFile", animation_rel)
        variant = records.render(parsed)
        result.texts[f"{animation_rel}.van"] = write_animations(exported)
        template_file = records.parse(data.read(template))[0].prop("animationFile")
        check_sequence(result, exported, game_reference(f"{template_file}.van") if template_file else [])
    else:
        result.findings.append(Finding("info", "no animations of its own; it plays the template's, which only works "
                                               "if the node names match"))
    result.texts[f"{target.gizmo_dir}/{stem}.variant"] = variant


def _plan_vehicle(result: Plan, target: ExportTarget):
    data = game.game_data()
    folder = f"vehicles/{target.vehicle_kind}/"
    template = result.root_obj.mt2.source_variant or next(iter(data.files(folder, ".def")), None)
    if not template or not data.exists(template):
        result.findings.append(Finding("error", f"no vehicle .def in {folder} to start from"))
        return
    stem = prefixed(target.mod_id, target.name)
    pads = collect_pads(result.root_obj) if has_own_pads(result.root_obj) else None
    result.texts[f"{folder}{stem}.def"] = derive_variant(data.read(template), stem, result.rel, pads,
                                                        label="mmoVehicleDefinition")
    if pads is not None:
        result.findings += [Finding(level, message) for level, message in pad_problems(pads)]
    game_tool = data.sources[-1].read(TOOL_FILE).decode("latin-1")
    result.texts[TOOL_FILE] = vehicle_tool_file(game_tool, _read_project_text(TOOL_FILE), stem,
                                                result.root_obj.mt2.standalone)
    _plan_display_name(result, target, f"vehicle_definition_{stem}_displayname")
    _plan_string(result, target, f"vehicle_definition_{stem}_description", result.root_obj.mt2.description, "Description")


def _plan_display_name(result: Plan, target: ExportTarget, key: str):
    _plan_string(result, target, key, result.root_obj.mt2.display_name, "Display name")


def _plan_string(result: Plan, target: ExportTarget, key: str, text: str, field_name: str):
    if not text:
        result.findings.append(Finding("info", f"set a {field_name}, or the game shows <<{key}>>"))
        return
    rel = strings_path(target.mod_id)
    result.texts[rel] = set_strings(result.texts.get(rel) or _read_project_text(rel), {key: text})


def _plan_weapon_category(result: Plan, target: ExportTarget):
    data = game.game_data()
    folder = f"weapons/{target.weapon_category}/"
    if any(name.startswith(folder) for name in data.sources[-1].names()):
        return
    key = f"weapon_category_{target.weapon_category}"
    display = result.root_obj.mt2.display_name
    if not display:
        result.findings.append(Finding("info", f"'{target.weapon_category}' is a new category; set a Display name, "
                                               f"or the game shows it as <<{key}>>"))
        return
    rel = strings_path(target.mod_id)
    result.texts[rel] = set_strings(_read_project_text(rel), {key: display})


def _plan_costume(result: Plan, target: ExportTarget):
    data = game.game_data()
    template = result.root_obj.get(TEMPLATE_KEY)
    if not template or not data.exists(template):
        result.findings.append(Finding("error", "a costume starts from a game costume; use Import costume"))
        return
    stem = prefixed(target.mod_id, target.name)
    placements = []
    own_parts = needs_own_parts(result.root_obj)
    for loose in loose_parts(result.root_obj):
        result.findings.append(Finding("warning", f"'{loose.name}' isn't a costume part yet, so it's left out; "
                                                  f"select it and use Make asset", loose.name))
    taken: dict[str, str] = {}
    for part in parts_of(result.root_obj):
        if part.parent is None or part.parent.mt2.role != "BONE":
            result.findings.append(Finding("warning", f"'{part.name}' isn't parented to a bone, so it's left out",
                                           part.name))
            continue
        bone = part.parent.get("mt2_node", part.parent.name)
        if bone in taken:
            result.findings.append(Finding("error", f"'{taken[bone]}' and '{part.name}' are both on {bone}; the game "
                                                    f"shows one part per bone, so join them (Ctrl + J)", part.name))
            continue
        taken[bone] = part.name
        if is_unchanged(part) and not own_parts:
            relative = part.parent.matrix_world.inverted() @ part.matrix_world
            placements.append(placement(part, part.mt2.source_path, relative.to_scale().x))
            continue
        part_plan = plan(part)
        result.parts.append(part_plan)
        result.findings += [Finding(f.level, f"{part.mt2.bone}: {f.message}", f.node or part.name)
                            for f in part_plan.findings if f.level != "info"]
        if part_plan.built is not None:
            placements.append(placement(part, part_plan.rel, part.mt2.model_scale if part.mt2.normalise else 1.0))
    rig = plan_rig(result, target)
    result.texts[result.rel] = write_costume(data.read(template), stem, placements, actor=rig,
                                             renames=bone_renames(result.root_obj))
    plan_creature_type(result, target, stem, rig)
    result.texts[f"costumes/{stem}.defaults"] = write_defaults([tuple(c.color) for c in result.root_obj.mt2.palette])
    _plan_display_name(result, target, f"costume_{stem}")


def _default_template(directory: str) -> str | None:
    files = variant_files(game.game_data(), directory)
    base = f"{directory}/base.variant"

    return base if base in files else (files[0] if files else None)


def _read_project_text(rel: str) -> str:
    return project.read_text(game.project_dir(), rel)


def write(result: Plan) -> list[str]:
    folder = game.project_dir()
    written = [rel for part in result.parts for rel in write(part)]
    if result.built is not None:
        model.save(result.built.root, folder / result.rel)
        written.append(result.rel)
    for rel, text in result.texts.items():
        project.write_text(folder, rel, text)
    for rel, data in result.files.items():
        project.write_bytes(folder, rel, data)
    project.record_export(folder, result.rel, result.root_obj.name)
    if not edits_game_gizmo(result.root_obj):
        result.root_obj.mt2.exported_path = result.rel
    written += write_art_pack(folder)
    game.forget()

    return written + [rel for rel in [*result.texts, *result.files] if rel not in written]


def write_art_pack(folder) -> list[str]:
    settings = bpy.context.scene.mt2
    data = game.game_data()
    if folder is None or data is None or not settings.mod_id:
        return []
    exported = [p for p in project.read_log(folder) if (folder / p).is_file()]
    vanilla = data.sources[-1].names()
    content = pack_content(exported, lambda prefix: any(n.startswith(prefix) for n in vanilla))
    categories = content["weaponCategories"] if settings.weapon_packs else []
    if not settings.art_pack_costumes:
        content["costumes"] = []
    rel = f"artpacks/{settings.mod_id}.vrt"
    written = [weapon_pack_path(c) for c in categories]
    if settings.art_pack and not is_empty(content):
        written.append(rel)
    for stale in (folder / "artpacks").glob("*.vrt") if (folder / "artpacks").is_dir() else ():
        managed = stale.name == f"{settings.mod_id}.vrt" or f"artpacks/{stale.name}".startswith(WEAPON_PACK_PREFIX)
        if managed and f"artpacks/{stale.name}" not in written:
            stale.unlink()
    if not written:
        return []
    strings_rel = strings_path(settings.mod_id)
    strings = {}
    if rel in written:
        project.write_text(folder, rel, art_pack(settings.mod_id, settings.art_pack_cost, settings.art_pack_exotic, content))
        strings[f"artpack_{settings.mod_id}_displayname"] = settings.art_pack_name or settings.mod_id
        if settings.art_pack_description:
            strings[f"artpack_{settings.mod_id}_description"] = settings.art_pack_description
    existing = _read_project_text(strings_rel)
    for category in categories:
        project.write_text(folder, weapon_pack_path(category), weapon_pack(category, settings.weapon_pack_cost))
        strings[f"weaponpack_{category}_displayname"] = _string(existing, f"weapon_category_{category}") or category
    project.write_text(folder, strings_rel, set_strings(existing, strings))

    return written


def _string(text: str, key: str) -> str | None:
    line = next((r for r in records.parse(text) if r.label == key), None) if text else None

    return line.first() if line else None


def show(scene, root_obj: bpy.types.Object, findings: list[Finding]):
    scene.mt2.findings_root = root_obj
    scene.mt2.findings.clear()
    for f in findings:
        item = scene.mt2.findings.add()
        item.level = f.level
        item.message = f.message
        item.object_name = f.node if f.node in bpy.data.objects else ""


def model_bytes(result: Plan) -> bytes:
    return model.write_model(result.built.root)
