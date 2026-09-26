import bpy

from . import shading


def show_palette(costume: bpy.types.Object):
    colors = [tuple(c.color) for c in costume.mt2.palette]
    if len(colors) < 8:
        return
    materials = {slot.material for obj in costume.children_recursive for slot in obj.material_slots if slot.material}
    for material in materials:
        if material.mt2.get("kind") == "costume":
            shading.set_palette(material, colors)
