import bpy
from mathutils import Matrix, Vector

from ..conversion.to_game import export_origin
from ..mt2model.axes import swap_position
from ..mt2model.pads import Entrance, Pad

NAME_KEY = "mt2_name"
OWN_PADS_KEY = "mt2_own_pads"


def has_own_pads(root: bpy.types.Object) -> bool:
    return bool(root.get(OWN_PADS_KEY)) or bool(pad_objects(root))


def create_pads(root: bpy.types.Object, pads: list[Pad], collection) -> list[bpy.types.Object]:
    root[OWN_PADS_KEY] = True
    placed = []
    to_world = export_origin(root).inverted()
    for pad in pads:
        pad_obj = helper_object(f"Pad {pad.name}", [swap_position(c) for c in pad.corners], "PAD", collection)
        _parent(pad_obj, root, to_world)
        pad_obj[NAME_KEY] = pad.name
        for entrance in pad.entrances:
            line = helper_object(
                f"Entrance {entrance.name}", [swap_position(p) for p in entrance.points], "ENTRANCE", collection
            )
            _parent(line, pad_obj, to_world)
            line[NAME_KEY] = entrance.name
        placed.append(pad_obj)

    return placed


def helper_object(name: str, points, role: str, collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    if role == "PAD" and len(points) >= 3:
        mesh.from_pydata(points, [], [tuple(range(len(points)))])
    else:
        mesh.from_pydata(points, [(i, i + 1) for i in range(len(points) - 1)], [])
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.mt2.role = role
    obj.display_type = "WIRE"
    obj.show_in_front = True
    obj.hide_render = True

    return obj


def _parent(obj: bpy.types.Object, parent: bpy.types.Object, to_world: Matrix):
    obj.parent = parent
    obj.matrix_world = to_world


def collect_pads(root: bpy.types.Object) -> list[Pad]:
    origin = export_origin(root)
    pads = []
    for pad_obj in _children(root, "PAD"):
        pad = Pad(_name(pad_obj), game_points(pad_obj, origin, closed=True))
        for line in _children(pad_obj, "ENTRANCE"):
            pad.entrances.append(Entrance(_name(line), game_points(line, origin, closed=False)))
        pads.append(pad)

    return pads


def pad_objects(root: bpy.types.Object) -> list[bpy.types.Object]:
    return list(_children(root, "PAD"))


def _children(obj: bpy.types.Object, role: str):
    return sorted((c for c in obj.children if c.mt2.role == role), key=lambda c: c.name)


def _name(obj: bpy.types.Object) -> str:
    stored = obj.get(NAME_KEY)
    if stored:
        return str(stored)
    for prefix in ("Pad ", "Entrance "):
        if obj.name.startswith(prefix):
            return obj.name[len(prefix) :]

    return obj.name


def game_points(obj: bpy.types.Object, origin: Matrix, closed: bool) -> list[tuple[float, float, float]]:
    mesh = obj.data
    matrix = origin @ obj.matrix_world
    order = _loop_order(mesh) if closed else _chain_order(mesh)

    return [tuple(float(x) for x in swap_position(matrix @ mesh.vertices[i].co)) for i in order]


def _loop_order(mesh) -> list[int]:
    if len(mesh.polygons):
        return list(mesh.polygons[0].vertices)

    return _chain_order(mesh)


def _chain_order(mesh) -> list[int]:
    if not len(mesh.edges):
        return list(range(len(mesh.vertices)))
    links: dict[int, list[int]] = {}
    for edge in mesh.edges:
        a, b = edge.vertices
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)
    ends = [v for v, near in links.items() if len(near) == 1]
    current = min(ends) if ends else min(links)
    order, previous = [current], None
    while True:
        following = [v for v in links[current] if v != previous and v not in order]
        if not following:
            break
        previous, current = current, following[0]
        order.append(current)

    return order


def new_pad(root: bpy.types.Object, location: Vector, size: float, collection) -> bpy.types.Object:
    half = size / 2
    corners = [(-half, -half, 0.0), (half, -half, 0.0), (half, half, 0.0), (-half, half, 0.0)]
    name = _free_name(root)
    pad = helper_object(f"Pad {name}", corners, "PAD", collection)
    _parent(pad, root, Matrix.Translation(location))
    pad[NAME_KEY] = name

    return pad


def new_entrance(pad: bpy.types.Object, collection) -> bpy.types.Object:
    points = [(0.0, -8.0, 0.0), (0.0, -5.0, 0.0), (0.0, -2.0, 0.0)]
    line = helper_object("Entrance base", points, "ENTRANCE", collection)
    centre = sum((pad.matrix_world @ v.co for v in pad.data.vertices), Vector()) / max(len(pad.data.vertices), 1)
    _parent(line, pad, Matrix.Translation(centre))
    line[NAME_KEY] = "base"

    return line


def _free_name(root: bpy.types.Object) -> str:
    used = {_name(p) for p in _children(root, "PAD")}
    for letter in "abcdefghijklmnopqrstuvwxyz":
        if letter not in used:
            return letter

    return f"pad{len(used)}"
