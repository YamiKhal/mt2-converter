import bpy

from ..colors.recent import MAX_RECENT
from ..colors.swatch_profiles import delete_profile, read_profiles, save_profile

DEFAULT_NAME = "Swatches"


class MT2_OT_save_swatches(bpy.types.Operator):
    bl_idname = "mt2.save_swatches"
    bl_label = "Save swatches"
    bl_description = (
        "Save the recent colors as a swatch profile, to load them again for other models and files. "
        "A profile with the same name is replaced"
    )
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Name", default=DEFAULT_NAME)
    ask: bpy.props.BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return len(context.scene.mt2.recent_colors) > 0

    def invoke(self, context, event):
        if not self.ask:
            return self.execute(context)
        self.name = context.scene.mt2.swatch_profile or DEFAULT_NAME

        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.name.strip()
        if not name:
            self.report({"ERROR"}, "Give the swatch profile a name")
            return {"CANCELLED"}
        settings = context.scene.mt2
        save_profile(name, [tuple(entry.color) for entry in settings.recent_colors])
        settings.swatch_profile = name
        self.report({"INFO"}, f"Saved '{name}'")

        return {"FINISHED"}


class MT2_OT_load_swatches(bpy.types.Operator):
    bl_idname = "mt2.load_swatches"
    bl_label = "Load swatches"
    bl_description = "Replace the recent colors with this swatch profile's colors"
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Name")

    def execute(self, context):
        colors = read_profiles().get(self.name)
        if colors is None:
            self.report({"ERROR"}, f"There's no swatch profile '{self.name}'")
            return {"CANCELLED"}
        settings = context.scene.mt2
        settings.recent_colors.clear()
        for color in colors[:MAX_RECENT]:
            settings.recent_colors.add().color = color
        settings.swatch_profile = self.name

        return {"FINISHED"}


class MT2_OT_new_swatches(bpy.types.Operator):
    bl_idname = "mt2.new_swatches"
    bl_label = "New swatches"
    bl_description = "Start an empty set of recent colors. Saved profiles stay as they are"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mt2
        settings.recent_colors.clear()
        settings.swatch_profile = ""

        return {"FINISHED"}


class MT2_OT_delete_swatches(bpy.types.Operator):
    bl_idname = "mt2.delete_swatches"
    bl_label = "Delete swatch profile"
    bl_description = "Delete this saved swatch profile. The recent colors stay"
    bl_options = {"REGISTER"}

    name: bpy.props.StringProperty(name="Name")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, message=f"Delete the swatch profile '{self.name}'?")

    def execute(self, context):
        delete_profile(self.name)
        if context.scene.mt2.swatch_profile == self.name:
            context.scene.mt2.swatch_profile = ""

        return {"FINISHED"}


class MT2_MT_swatches(bpy.types.Menu):
    bl_idname = "MT2_MT_swatches"
    bl_label = "Swatches"
    bl_description = "Save the recent colors as a swatch profile, load one, or start a new set"

    def draw(self, context):
        layout = self.layout
        active = context.scene.mt2.swatch_profile
        profiles = read_profiles()
        if active in profiles:
            save = layout.operator("mt2.save_swatches", text=f"Save to '{active}'", icon="FILE_TICK")
            save.name, save.ask = active, False
        layout.operator("mt2.save_swatches", text="Save as...", icon="ADD")
        layout.operator("mt2.new_swatches", text="New", icon="FILE_NEW")
        if profiles:
            layout.separator()
        for name in sorted(profiles, key=str.lower):
            icon = "CHECKMARK" if name == active else "COLOR"
            layout.operator("mt2.load_swatches", text=name, icon=icon).name = name
        if active in profiles:
            layout.separator()
            layout.operator("mt2.delete_swatches", text=f"Delete '{active}'", icon="TRASH").name = active


CLASSES = (MT2_OT_save_swatches, MT2_OT_load_swatches, MT2_OT_new_swatches, MT2_OT_delete_swatches, MT2_MT_swatches)
