import math
from dataclasses import dataclass

from .assets import SPECIAL_MATERIALS, AssetType
from .footprint import building_footprint, model_points, scenery_footprint
from .formats import FORMATS, layout
from .materials import PALETTE_SLOTS, MaterialCatalog
from .model import MAX_VERTICES, Fragment, Node


@dataclass
class Finding:
    level: str
    message: str
    node: str = ""
    material: str = ""


def validate(root: Node, asset: AssetType, catalog: MaterialCatalog, replaces_vanilla: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    total = 0
    for node, _ in root.walk():
        for fragment in node.fragments:
            total += len(fragment.vertices)
            findings += _check_fragment(node.name, fragment, asset, catalog)
    if total > asset.budget:
        findings.append(
            Finding("warning", f"{total} vertices; vanilla {asset.label.lower()} models stay under {asset.budget}")
        )
    if total:
        findings += _check_shape(root, asset)
    else:
        findings.append(Finding("error", "the model has no geometry"))
    if replaces_vanilla:
        findings.append(
            Finding(
                "warning",
                "this path replaces a vanilla model for every player of the mod; a new name adds a variant instead",
            )
        )

    return findings


def _check_fragment(node: str, fragment: Fragment, asset: AssetType, catalog: MaterialCatalog) -> list[Finding]:
    def found(level: str, message: str) -> Finding:
        return Finding(level, message, node, fragment.material)

    out = []
    name = fragment.material
    if fragment.format not in FORMATS:
        return [found("error", f"unknown vertex format '{fragment.format}'")]
    if not name:
        out.append(found("error", "a fragment has no material name"))
    elif name in SPECIAL_MATERIALS:
        if name not in asset.special:
            out.append(
                found(
                    "error",
                    f"'{name}' fragments only work in "
                    f"{'dungeon tiles' if name in ('collision', 'navmesh') else 'scenery'}; "
                    f"here the game would draw them",
                )
            )
    elif catalog.get(name) is None:
        out.append(
            found("error", f"material '{name}' has no materials/{name}.mat; the game closes when it loads this model")
        )
    if not fragment.vertices or not fragment.indices:
        out.append(found("error", "empty fragment"))

        return out
    if len(fragment.vertices) > MAX_VERTICES:
        out.append(
            found("error", f"{len(fragment.vertices)} vertices in one fragment; the game reads at most {MAX_VERTICES}")
        )
    if len(fragment.indices) % 3:
        out.append(found("error", "the index count is not a multiple of 3"))
    if min(fragment.indices) < 0 or max(fragment.indices) >= len(fragment.vertices):
        out.append(found("error", "a triangle points at a vertex that doesn't exist"))
    if any(not math.isfinite(x) for v in fragment.vertices for x in v):
        out.append(found("error", "some vertex values are NaN or infinite"))
    info = catalog.get(name) if name not in SPECIAL_MATERIALS else None
    if info is not None and info.texture and not catalog.file_exists(info.texture):
        out.append(
            found(
                "error",
                f"material '{name}' uses the texture '{info.texture}', which isn't in the game or "
                f"the mod; the game most likely closes (it asserts when a file can't be opened)",
            )
        )
    if info is not None:
        out += [
            found(level, message) for level, message in _check_material_use(fragment, info.kind, info.textured, asset)
        ]

    return out


def _check_material_use(fragment: Fragment, kind: str, textured: bool, asset: AssetType):
    lay = layout(fragment.format)
    if asset.coloring == "costume" and kind != "costume":
        yield "warning", f"costume parts use the 'costume' material; '{fragment.material}' ignores the palette"
    if asset.coloring == "vertex" and kind != "vertex":
        yield "warning", f"'{fragment.material}' is a {kind} material; this asset type expects vertex colors"
    if kind in PALETTE_SLOTS:
        if lay.texel is None:
            yield "error", f"'{fragment.material}' picks colors from UVs, but this fragment has none"
        elif any(not 0.0 <= v[lay.texel] <= 1.0 for v in fragment.vertices):
            yield "info", "some palette U values are outside 0-1 and wrap to another slot"
    if textured and lay.texel is None:
        yield "warning", f"'{fragment.material}' is textured, but this fragment has no UVs, so it shows one texel"
    if kind == "vertex" and lay.color is None:
        yield "info", "no vertex colors; the game draws this fragment in its default color"
    if lay.color is not None and any(v[lay.color + 3] < 0.999 for v in fragment.vertices):
        yield "info", "some vertex colors have alpha below 1"


def _check_shape(root: Node, asset: AssetType) -> list[Finding]:
    points = model_points(root)
    if not points:
        return []
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    out = []
    if asset.key in ("scenery", "building") and low[1] > 0.5:
        out.append(Finding("warning", f"the lowest point is {low[1]:.2f} above the origin; the model will float"))
    if asset.key == "scenery" and scenery_footprint(root) is None:
        out.append(Finding("info", "small and flat enough that the game gives it no footprint; NPCs walk through it"))
    if asset.key == "building" and building_footprint(root) is None:
        out.append(Finding("warning", "no geometry below 2 units high, so the building gets no footprint"))
    if asset.key == "weapon" and any(low[i] > 0.25 or high[i] < -0.25 for i in range(3)):
        out.append(Finding("warning", "the origin is far from the model; weapons are held at their origin"))
    if asset.key == "costume_part":
        extent = max(high[i] - low[i] for i in range(3))
        if not 0.5 <= extent <= 2.0:
            out.append(
                Finding(
                    "info",
                    f"largest side is {extent:.3f}; vanilla parts are normalised to 1.0 "
                    f"(the exporter can normalise and report modelScale {extent:.4f})",
                )
            )

    return out


def has_errors(findings: list[Finding]) -> bool:
    return any(f.level == "error" for f in findings)
