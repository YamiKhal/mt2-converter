import bpy

from . import guides, operators, panels, preferences, properties, updates
from .operators.theme import draw_theme_context_menu

CLASSES = (
    *properties.CLASSES,
    *preferences.CLASSES,
    *operators.CLASSES,
    *panels.CLASSES,
)


def _menu_import(self, context):
    self.layout.operator("mt2.import_file", text="MMORPG Tycoon 2 (.vmb)")


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    properties.register_properties()
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)
    bpy.types.UI_MT_button_context_menu.append(draw_theme_context_menu)
    guides.register()
    updates.register()


def unregister():
    updates.unregister()
    guides.unregister()
    bpy.types.UI_MT_button_context_menu.remove(draw_theme_context_menu)
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    properties.unregister_properties()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
