from pathlib import Path

from .. import game, mod_folder
from ..mt2model.naming import clean_word, prefixed

TEXTURE_FOLDER = "textures"
TEXTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tga", ".bmp")


def write_textured_material(folder: Path, mod_id: str, name: str, image: bytes, suffix: str) -> str:
    material = prefixed(mod_id, clean_word(name) or "texture")
    texture_rel = f"{TEXTURE_FOLDER}/{material}{suffix.lower()}"
    material_rel = f"materials/{material}.mat"
    if (folder / material_rel).exists():
        raise FileExistsError(f"{material_rel} already exists; pick another name")
    (folder / TEXTURE_FOLDER).mkdir(parents=True, exist_ok=True)
    (folder / texture_rel).write_bytes(image)
    mod_folder.write_text(folder, material_rel, textured_material(texture_rel))
    game.forget()

    return material


def textured_material(texture_rel: str) -> str:
    return (
        "Material {\n"
        "\tcolor 1.0 1.0 1.0 1.0\n"
        "\tmode lit\n"
        f'\ttexture "{texture_rel}"\n'
        '\tshader "tint_v.glsl" "tint_f.glsl"\n'
        "}\n"
    )
