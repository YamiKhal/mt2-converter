import bpy

from . import (guides, ops_animation, ops_colors, ops_convert, ops_export, ops_helpers, ops_import, ops_materials,
               ops_paint, ops_palette, ops_rig, ops_select, ops_shading, ops_swatches, ops_theme, ops_updates,
               preferences, settings, ui, updates)

CLASSES = (
    *settings.CLASSES,
    *preferences.CLASSES,
    *ops_import.CLASSES,
    *ops_export.CLASSES,
    *ops_paint.CLASSES,
    *ops_shading.CLASSES,
    *ops_palette.CLASSES,
    *ops_colors.CLASSES,
    *ops_swatches.CLASSES,
    *ops_select.CLASSES,
    *ops_helpers.CLASSES,
    *ops_materials.CLASSES,
    *ops_animation.CLASSES,
    *ops_rig.CLASSES,
    *ops_theme.CLASSES,
    *ops_convert.CLASSES,
    *ops_updates.CLASSES,
    *ui.CLASSES,
)


def _menu_import(self, context):
    self.layout.operator("mt2.import_file", text="MMORPG Tycoon 2 (.vmb)")


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    settings.register_properties()
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)
    guides.register()
    updates.register()


def unregister():
    updates.unregister()
    guides.unregister()
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    settings.unregister_properties()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
