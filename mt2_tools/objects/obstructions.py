import bpy

from ..conversion.to_game import export_origin
from ..mt2model.axes import swap_ground


def create_obstruction_shape(root: bpy.types.Object, polygons, collection) -> bpy.types.Object:
    vertices, faces = [], []
    for polygon in polygons:
        faces.append(tuple(range(len(vertices), len(vertices) + len(polygon))))
        vertices += [(*swap_ground(point), 0.0) for point in reversed(polygon)]
    mesh = bpy.data.meshes.new(f"{root.name} obstruction")
    mesh.from_pydata(vertices, [], faces)
    shape = bpy.data.objects.new(f"{root.name} obstruction", mesh)
    collection.objects.link(shape)
    shape.parent = root
    shape.matrix_world = export_origin(root).inverted()
    shape.mt2.role = "OBSTRUCTION"
    shape.display_type = "WIRE"
    shape.hide_render = True

    return shape
