import bpy
from mathutils import Matrix, Quaternion

from ..conversion.to_game import export_origin
from ..mt2model.axes import swap_position, swap_rotation

FLIGHT_POINTS = "buildings/flightpoint"
SPOT_SIZE = 1.5


def is_flight_point(root: bpy.types.Object) -> bool:
    return root.mt2.asset == "building" and root.mt2.building_dir == FLIGHT_POINTS


def spot_of(root: bpy.types.Object) -> bpy.types.Object | None:
    return next((c for c in root.children if c.mt2.role == "CREATURE"), None)


def create_spot(root: bpy.types.Object, offset, rotation, collection) -> bpy.types.Object:
    spot = bpy.data.objects.new("Creature spot", None)
    collection.objects.link(spot)
    spot.empty_display_type = "ARROWS"
    spot.empty_display_size = SPOT_SIZE
    spot.mt2.role = "CREATURE"
    spot.rotation_mode = "QUATERNION"
    spot.parent = root
    x, y, z, w = swap_rotation(rotation)
    local = Matrix.Translation(swap_position(offset)) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
    spot.matrix_world = export_origin(root).inverted() @ local

    return spot


def spot_placement(root: bpy.types.Object, spot: bpy.types.Object):
    location, rotation, _ = (export_origin(root) @ spot.matrix_world).decompose()

    return swap_position(location), swap_rotation((rotation.x, rotation.y, rotation.z, rotation.w))
