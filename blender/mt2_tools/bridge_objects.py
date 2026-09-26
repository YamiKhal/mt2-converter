import bpy

from .convert_out import export_origin
from .mt2model.axes import swap_position
from .mt2model.bridges import Bridge
from .obstruction_objects import create_obstruction_shape
from .pad_objects import game_points, helper_object

RAMP_PATH = "RAMP_PATH"
BRIDGE_DATA_KEY = "mt2_bridge_data"
NEW_RAMP_PATH = [(0.0, 0.0, 0.0), (0.0, 0.0, 2.0), (0.0, 5.0, 15.0), (0.0, 5.0, 25.0)]


def is_ramp(root: bpy.types.Object | None) -> bool:
    return root is not None and root.mt2.asset == "bridge" and root.mt2.bridge_piece == "ramp"


def is_bridge_span(root: bpy.types.Object | None) -> bool:
    return root is not None and root.mt2.asset == "bridge" and root.mt2.bridge_piece == "bridge"


def ramp_path_object(root: bpy.types.Object) -> bpy.types.Object | None:
    return next((c for c in root.children if c.mt2.role == RAMP_PATH), None)


def create_ramp_path(root: bpy.types.Object, points, collection) -> bpy.types.Object:
    line = helper_object("Ramp path", [swap_position(p) for p in points], RAMP_PATH, collection)
    line.parent = root
    line.matrix_world = export_origin(root).inverted()

    return line


def ramp_path_points(root: bpy.types.Object) -> list[tuple[float, float, float]]:
    line = ramp_path_object(root)

    return game_points(line, export_origin(root), closed=False) if line else []


def import_bridge_data(root: bpy.types.Object, bridge: Bridge, collection):
    root[BRIDGE_DATA_KEY] = True
    if is_ramp(root):
        if len(bridge.ramp_path) >= 2:
            create_ramp_path(root, bridge.ramp_path, collection)
        return
    root.mt2.fully_obstructed = bridge.fully_obstructed
    if bridge.obstruction:
        create_obstruction_shape(root, bridge.obstruction, collection)
