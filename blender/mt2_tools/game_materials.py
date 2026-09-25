import os
import tempfile
from pathlib import PurePosixPath

import bpy

from . import game, shading
from .mt2model.assets import SPECIAL_MATERIALS


def material_for(name: str) -> bpy.types.Material:
    return shading.game_material(name, kind_of(name), texture_image(name))


def kind_of(name: str) -> str:
    if name in SPECIAL_MATERIALS:
        return name
    if name == "emissive":
        return "emissive"
    catalog = game.catalog()
    info = catalog.get(name) if catalog else None

    return info.kind if info else "vertex"


def texture_image(name: str) -> bpy.types.Image | None:
    catalog = game.catalog()
    info = catalog.get(name) if catalog else None
    if info is None or not info.textured or not info.texture:
        return None
    rel = PurePosixPath(info.texture.replace("\\", "/"))
    existing = bpy.data.images.get(f"MT2 {rel.as_posix()}")
    if existing is not None:
        return existing
    data = game.game_data()
    if data is None or not data.exists(rel.as_posix()):
        return None

    return _load_packed(f"MT2 {rel.as_posix()}", data.read(rel.as_posix()), rel.suffix)


def _load_packed(name: str, raw: bytes, suffix: str) -> bpy.types.Image | None:
    handle, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(raw)
        image = bpy.data.images.load(path)
        image.pack()
        image.name = name
    except RuntimeError:
        return None
    finally:
        os.remove(path)

    return image
