from dataclasses import dataclass, field

import bpy

from . import convert_out, game, project
from .mt2model import model
from .mt2model.assets import asset_type
from .mt2model.axes import AXES_VERSION
from .mt2model.costume import normalise
from .mt2model.footprint import is_convex
from .mt2model.i18n import set_strings, strings_path
from .mt2model.naming import ExportTarget, model_path, prefixed, target_problems
from .mt2model.obstruction import obs_file_name, write_obstruction
from .mt2model.validate import Finding, has_errors, validate
from .mt2model.variants import building_kinds, derive_variant, display_name_key, variant_files


@dataclass
class Plan:
    root_obj: bpy.types.Object
    rel: str = ""
    built: convert_out.Built | None = None
    findings: list[Finding] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.built is not None and not has_errors(self.findings)


def target_for(root_obj: bpy.types.Object) -> ExportTarget:
    s = root_obj.mt2

    return ExportTarget(
        asset=s.asset, name=s.name or root_obj.name, mod_id=bpy.context.scene.mt2.mod_id,
        scenery_type=s.scenery_type, weapon_category=s.weapon_category, item_level=s.item_level,
        costume_set=s.costume_set, bone=s.bone, theme=s.theme, slot=s.slot, building_dir=s.building_dir,
        wall_piece=s.wall_piece, tag_place=s.tag_place, tag_kind=s.tag_kind, tag_small=s.tag_small,
        tag_extra=s.tag_extra.split(), raw_path=s.raw_path,
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
    result.rel = model_path(target)
    other = _other_asset_at(root_obj, result.rel)
    if other is not None:
        result.findings.append(Finding("error", f"'{other.name}' in this file also exports to {result.rel}; "
                                                f"give one of them another name", other.name))
    asset = asset_type(target.asset)
    result.built = convert_out.build(root_obj, asset, game.catalog())
    result.findings += [Finding(level, message, object_name) for level, message, object_name in result.built.notes]
    if target.asset == "costume_part" and root_obj.mt2.normalise:
        scale = normalise(result.built.root)
        root_obj.mt2.model_scale = scale
        result.findings.append(Finding("info", f"normalised; use modelScale {scale:.6f} for this part in the .costume"))
    result.findings += validate(result.built.root, asset, game.catalog(), replaces_vanilla=data.is_vanilla(result.rel))
    previous = root_obj.mt2.exported_path
    if previous and previous != result.rel:
        result.findings.append(Finding("error", f"this asset was exported as {previous}. Saves find models by file name, "
                                                f"so renaming breaks it where players placed it. "
                                                f"Use 'Forget previous export' if this is meant to be a new model"))
    _plan_obstruction(result, target)
    if target.asset == "building":
        _plan_variant(result, target)
    if target.asset == "weapon":
        _plan_weapon_category(result, target)

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
    if not polygons:
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
    result.texts[f"{target.building_dir}/{stem}.variant"] = derive_variant(data.read(template), stem, result.rel)
    result.findings.append(Finding("info", f"NPC pads and entrances copied from {template}; keep the same door and floor layout"))
    display = result.root_obj.mt2.display_name
    kind = next((k for k in building_kinds(data) if k.directory == target.building_dir), None)
    if display and kind:
        rel = strings_path(target.mod_id)
        existing = _read_project_text(rel)
        result.texts[rel] = set_strings(existing, {display_name_key(kind.key, stem): display})


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


def _default_template(directory: str) -> str | None:
    files = variant_files(game.game_data(), directory)
    base = f"{directory}/base.variant"

    return base if base in files else (files[0] if files else None)


def _read_project_text(rel: str) -> str:
    folder = game.project_dir()
    path = folder / rel if folder else None

    return path.read_text(encoding="utf-8") if path and path.is_file() else ""


def write(result: Plan) -> list[str]:
    folder = game.project_dir()
    model.save(result.built.root, folder / result.rel)
    for rel, text in result.texts.items():
        project.write_text(folder, rel, text)
    project.record_export(folder, result.rel, result.root_obj.name)
    result.root_obj.mt2.exported_path = result.rel
    game.forget()

    return [result.rel, *result.texts]


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
