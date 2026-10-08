from pathlib import Path

import bpy

from .mt2model.gamedata import GameData
from .mt2model.materials import MaterialCatalog

ADDON = __package__


class _Cache:
    key: tuple | None = None
    data: GameData | None = None
    catalog: MaterialCatalog | None = None


def preferences():
    return bpy.context.preferences.addons[ADDON].preferences


def project_dir() -> Path | None:
    text = bpy.context.scene.mt2.project_dir

    return Path(bpy.path.abspath(text)) if text else None


def game_data() -> GameData | None:
    game = preferences().game_path
    project = project_dir()
    key = (game, str(project))
    if _Cache.key != key:
        _Cache.key = key
        try:
            overlays = [project] if project and project.is_dir() else []
            _Cache.data = GameData.open(game, overlays) if game else None
        except (FileNotFoundError, OSError):
            _Cache.data = None
        _Cache.catalog = MaterialCatalog(_Cache.data) if _Cache.data else None
        bpy.app.timers.register(refresh_material_names, first_interval=0.0)

    return _Cache.data


def catalog() -> MaterialCatalog | None:
    game_data()

    return _Cache.catalog


def forget():
    _Cache.key = None


def rescan():
    if _Cache.data is None:
        return
    _Cache.data.rescan()
    _Cache.catalog = MaterialCatalog(_Cache.data)
    bpy.app.timers.register(refresh_material_names, first_interval=0.0)


def refresh_material_names():
    manager = bpy.context.window_manager
    if manager is None or not hasattr(manager, "mt2_materials"):
        return
    names = manager.mt2_materials
    names.clear()
    if _Cache.data is not None:
        for name in sorted(_Cache.data.materials()):
            names.add().name = name

    return
