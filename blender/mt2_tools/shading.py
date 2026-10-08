import bpy

from .mt2model.colors import srgb_to_linear
from .mt2model.costume import GREY_PALETTE
from .mt2model.materials import PALETTE_SLOTS

SPECIAL_COLORS = {
    "light": (1.0, 0.85, 0.3, 1.0),
    "obstruction": (1.0, 0.2, 0.2, 1.0),
    "collision": (0.2, 0.6, 1.0, 1.0),
    "navmesh": (0.2, 1.0, 0.6, 1.0),
}


def game_material(name: str, kind: str, image: bpy.types.Image | None = None,
                  glow: bool = False) -> bpy.types.Material:
    material = next((m for m in bpy.data.materials if m.mt2.game_name == name), None)
    if material is None:
        material = bpy.data.materials.new(name)
        material.mt2.game_name = name
        setup(material, kind, image=image, glow=glow)

    return material


def setup(material: bpy.types.Material, kind: str, palette=None, image: bpy.types.Image | None = None,
          glow: bool = False):
    if material.node_tree is None:
        material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (600, 0)
    if kind in SPECIAL_COLORS:
        _flat(tree, output, SPECIAL_COLORS[kind])
        material.diffuse_color = SPECIAL_COLORS[kind]
    elif kind in PALETTE_SLOTS:
        _palette(tree, output, palette or GREY_PALETTE, PALETTE_SLOTS[kind], glow)
    else:
        _vertex(tree, output, emissive=kind == "emissive", image=image)
    material.mt2["kind"] = kind


def set_palette(material: bpy.types.Material, palette):
    ramp = material.node_tree.nodes.get("MT2 Palette") if material.node_tree else None
    if ramp is None:
        return
    for element, color in zip(ramp.color_ramp.elements, palette):
        element.color = srgb_to_linear(color)


def _principled(tree):
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    bsdf.inputs["Roughness"].default_value = 0.8

    return bsdf


def _vertex(tree, output, emissive: bool, image: bpy.types.Image | None):
    attribute = tree.nodes.new("ShaderNodeVertexColor")
    attribute.location = (0, 0)
    if image is not None:
        _textured(tree, output, attribute, image)
        return
    if emissive:
        shader = tree.nodes.new("ShaderNodeEmission")
        shader.location = (300, 0)
        shader.inputs["Strength"].default_value = 2.0
        tree.links.new(attribute.outputs["Color"], shader.inputs["Color"])
        tree.links.new(shader.outputs[0], output.inputs["Surface"])
        return
    bsdf = _principled(tree)
    tree.links.new(attribute.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(bsdf.outputs[0], output.inputs["Surface"])


def _textured(tree, output, attribute, image: bpy.types.Image):
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.location = (0, 250)
    multiply = tree.nodes.new("ShaderNodeMix")
    multiply.data_type = "RGBA"
    multiply.blend_type = "MULTIPLY"
    multiply.location = (150, 100)
    multiply.inputs["Factor"].default_value = 1.0
    bsdf = _principled(tree)
    tree.links.new(texture.outputs["Color"], multiply.inputs[6])
    tree.links.new(attribute.outputs["Color"], multiply.inputs[7])
    tree.links.new(multiply.outputs[2], bsdf.inputs["Base Color"])
    tree.links.new(bsdf.outputs[0], output.inputs["Surface"])


def _flat(tree, output, color):
    shader = tree.nodes.new("ShaderNodeEmission")
    shader.location = (300, 0)
    shader.inputs["Color"].default_value = color
    tree.links.new(shader.outputs[0], output.inputs["Surface"])


def _palette(tree, output, palette, slots: int, glow: bool):
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.location = (-600, 0)
    split = tree.nodes.new("ShaderNodeSeparateXYZ")
    split.location = (-400, 0)
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.name = "MT2 Palette"
    ramp.location = (-200, 150)
    ramp.color_ramp.interpolation = "CONSTANT"
    elements = ramp.color_ramp.elements
    elements[0].position = 0.0
    elements[1].position = 1 / slots
    for index in range(2, slots):
        elements.new(index / slots)
    for index, element in enumerate(elements):
        element.color = srgb_to_linear(palette[index % len(palette)])
    shade = tree.nodes.new("ShaderNodeMapRange")
    shade.location = (-200, -150)
    shade.inputs["To Min"].default_value = 1.0
    shade.inputs["To Max"].default_value = 0.5
    multiply = tree.nodes.new("ShaderNodeMix")
    multiply.data_type = "RGBA"
    multiply.blend_type = "MULTIPLY"
    multiply.location = (100, 0)
    multiply.inputs["Factor"].default_value = 1.0
    bsdf = _principled(tree)
    tree.links.new(uv.outputs["UV"], split.inputs[0])
    tree.links.new(split.outputs["X"], ramp.inputs["Fac"])
    tree.links.new(split.outputs["Y"], shade.inputs["Value"])
    tree.links.new(ramp.outputs["Color"], multiply.inputs[6])
    tree.links.new(shade.outputs["Result"], multiply.inputs[7])
    tree.links.new(multiply.outputs[2], bsdf.inputs["Base Color"])
    if glow:
        tree.links.new(multiply.outputs[2], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.0
    tree.links.new(bsdf.outputs[0], output.inputs["Surface"])
