import bpy
from mathutils import Matrix, Quaternion, Vector

from .convert_out import export_origin
from .mt2model.axes import swap_position, swap_rotation
from .mt2model.dungeons import Socket

ORDER_KEY = "mt2_order"


def create_sockets(root: bpy.types.Object, sockets: list[Socket], collection):
    to_world = export_origin(root).inverted()
    for index, socket in enumerate(sockets):
        x, y, z, w = swap_rotation(socket.orientation)
        local = Matrix.Translation(Vector(swap_position(socket.position))) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
        new_socket(root, to_world @ local, " ".join(socket.tags), collection)[ORDER_KEY] = index


def new_socket(root: bpy.types.Object, world: Matrix, tags: str, collection) -> bpy.types.Object:
    obj = bpy.data.objects.new(f"Socket {tags}", None)
    collection.objects.link(obj)
    obj.empty_display_type = "SINGLE_ARROW"
    obj.empty_display_size = 1.0
    obj.mt2.role = "SOCKET"
    obj.mt2.socket_tags = tags
    obj.parent = root
    obj.matrix_world = world

    return obj


def collect_sockets(root: bpy.types.Object) -> list[Socket]:
    origin = export_origin(root)
    sockets = []
    found = [c for c in root.children_recursive if c.mt2.role == "SOCKET"]
    for obj in sorted(found, key=lambda o: (o.get(ORDER_KEY, len(found)), o.name)):
        local = origin @ obj.matrix_world
        rotation = local.to_quaternion()
        sockets.append(Socket(
            tags=obj.mt2.socket_tags.split(),
            position=tuple(float(v) for v in swap_position(local.translation)),
            orientation=tuple(float(v) for v in swap_rotation((rotation.x, rotation.y, rotation.z, rotation.w))),
        ))

    return sockets
