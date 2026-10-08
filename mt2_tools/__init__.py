import bpy

from . import guides, operators, panels, preferences, properties, updates

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
    guides.register()
    updates.register()


def unregister():
    updates.unregister()
    guides.unregister()
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    properties.unregister_properties()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
