from . import game, project
from .bridge_objects import BRIDGE_DATA_KEY, is_bridge_span, is_ramp, ramp_path_object, ramp_path_points
from .mt2model.bridges import BRIDGE_LENGTH, set_obstruction, set_ramp_path, variant_path
from .mt2model.footprint import is_convex
from .mt2model.validate import Finding

GROUND_TOLERANCE = 0.5
END_TOLERANCE = 1.0


def plan_bridge(result, target):
    root = result.root_obj
    polygons = result.built.obstruction
    if is_ramp(root) and polygons:
        result.findings.append(Finding("warning", "obstruction shapes only work on the bridge piece; they are not exported"))
    if not _has_bridge_data(root, polygons):
        return
    rel = variant_path(target.theme)
    vanilla = game.game_data().sources[-1]
    replaces_game = vanilla.exists(rel)
    text = project.read_text(game.project_dir(), rel) or (vanilla.read(rel).decode("latin-1") if replaces_game else "")
    if not text:
        result.findings.append(Finding("error", f"there's no bridge theme '{target.theme}' to add the ramp path and "
                                                f"obstruction to; make one with New theme"))
        return
    if is_ramp(root):
        _plan_ramp_path(result, rel, text, replaces_game)
    else:
        _plan_obstruction(result, rel, text, polygons, replaces_game)


def _has_bridge_data(root, polygons) -> bool:
    if is_ramp(root):
        return ramp_path_object(root) is not None

    return is_bridge_span(root) and (bool(polygons) or bool(root.get(BRIDGE_DATA_KEY)) or root.mt2.fully_obstructed)


def _plan_ramp_path(result, rel: str, text: str, replaces_game: bool):
    points = ramp_path_points(result.root_obj)
    name = ramp_path_object(result.root_obj).name
    if len(points) < 2:
        result.findings.append(Finding("error", "the ramp path needs at least 2 points", name))
        return
    if abs(points[0][1]) > GROUND_TOLERANCE:
        result.findings.append(Finding("warning", "the ramp path should start on the ground, at height 0", name))
    model_end = _model_end(result.built.root)
    if model_end is not None and abs(points[-1][2] - model_end) > END_TOLERANCE:
        result.findings.append(Finding("warning", f"the ramp path ends {points[-1][2]:.1f} along the ramp, but the ramp "
                                                  f"model ends at {model_end:.1f}; characters step onto the bridge where "
                                                  f"the path ends", name))
    result.texts[rel] = set_ramp_path(text, points, replaces_game)


def _plan_obstruction(result, rel: str, text: str, polygons, replaces_game: bool):
    for polygon in polygons:
        if not is_convex(polygon):
            result.findings.append(Finding("error", "every obstruction face must be convex; split concave shapes into "
                                                    "several faces"))
            return
    along = [z for polygon in polygons for _, z in polygon]
    if along and (min(along) < -END_TOLERANCE or max(along) > BRIDGE_LENGTH + END_TOLERANCE):
        result.findings.append(Finding("warning", f"obstruction shapes should stay within the bridge's length, 0 to "
                                                  f"{BRIDGE_LENGTH:.0f}; the game bends them along the bridge"))
    result.texts[rel] = set_obstruction(text, polygons, result.root_obj.mt2.fully_obstructed, replaces_game)


def _model_end(root) -> float | None:
    along = [v[2] for node, _ in root.walk() for fragment in node.fragments for v in fragment.vertices]

    return max(along) if along else None
