COSTUME_SHADER = "costume_f.glsl"

_PALETTE_DONE = "\tcolor.rgb = mix( color.rgb, frontColor.rgb, frontColor.a );\n"
_SHADING_DONE = "\tif ( distanceCull )\n"


def glow_material(costume_material: str, fragment_shader: str) -> str:
    lines = []
    for line in costume_material.splitlines():
        words = line.strip().split()
        if words[:1] == ["glow"]:
            continue
        if words[:1] == ["shader"]:
            lines.append("\tglow true")
            line = line.replace(f'"{COSTUME_SHADER}"', f'"{fragment_shader}"')
        lines.append(line)

    return "\n".join(lines) + "\n"


def glow_shader(costume_shader: str) -> str:
    text = costume_shader.replace("\r\n", "\n")
    if _PALETTE_DONE not in text or _SHADING_DONE not in text:
        raise ValueError("The game's costume shader changed, so the glow shader can't be made from it")
    text = text.replace(_PALETTE_DONE, _PALETTE_DONE + "\tvec3 glowColor = color.rgb;\n", 1)
    unlit = ("\tcolor.rgb = max( color.rgb, mix( glowColor, finalFogColor, finalFogFactor ) );\n"
             "\tnowGlow = 1.0;\n\n")

    return text.replace(_SHADING_DONE, unlit + _SHADING_DONE, 1)
