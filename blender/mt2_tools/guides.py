import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .convert_out import asset_root

CELL = 3.0
WALL_LENGTH = 50.0
BRIDGE_LENGTHS = {"bridge": 60.0, "ramp": 50.0}
COLOR = (0.35, 0.8, 1.0, 0.6)

Line = tuple[Vector, Vector]

_handle: list = []


def guide_lines(root: bpy.types.Object) -> list[Line]:
    asset = root.mt2.asset
    if asset == "modular":
        return _box(Vector((-CELL / 2, -CELL / 2, -CELL / 2)), Vector((CELL / 2, CELL / 2, CELL / 2)))
    if asset == "wall":
        return _run(WALL_LENGTH, 2.0)
    if asset == "bridge":
        return _run(BRIDGE_LENGTHS.get(root.mt2.bridge_piece, WALL_LENGTH), 8.0)

    return []


def _box(low: Vector, high: Vector) -> list[Line]:
    corners = [Vector((x, y, z)) for x in (low.x, high.x) for y in (low.y, high.y) for z in (low.z, high.z)]
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]

    return [(corners[a], corners[b]) for a, b in edges]


def _run(length: float, half_width: float) -> list[Line]:
    lines = [(Vector((0, 0, 0)), Vector((0, length, 0)))]
    for y in (0.0, length):
        lines.append((Vector((-half_width, y, 0)), Vector((half_width, y, 0))))

    return lines


def _draw():
    context = bpy.context
    root = asset_root(context.active_object)
    if root is None or not context.scene.mt2.show_guides:
        return
    lines = guide_lines(root)
    if not lines:
        return
    origin = root.matrix_world.translation
    points = [tuple(origin + p) for line in lines for p in line]
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    region = context.region
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 1.5)
    shader.uniform_float("color", COLOR)
    gpu.state.blend_set("ALPHA")
    batch_for_shader(shader, "LINES", {"pos": points}).draw(shader)
    gpu.state.blend_set("NONE")


def register():
    if not _handle and not bpy.app.background:
        _handle.append(bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_VIEW"))


def unregister():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), "WINDOW")
