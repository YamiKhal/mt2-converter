import bpy

from . import game
from .mt2model import detect


def _changed(self, context):
    game.forget()


class MT2_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    game_path: bpy.props.StringProperty(
        name="Game folder",
        description="MMORPG Tycoon 2 install folder (the one holding Data\\MMORPG.zip), or an extracted GameData folder",
        subtype="DIR_PATH",
        update=_changed,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "game_path")
        layout.operator("mt2.detect_paths", icon="VIEWZOOM")


class MT2_OT_detect_paths(bpy.types.Operator):
    bl_idname = "mt2.detect_paths"
    bl_label = "Detect game"
    bl_description = "Find the game through Steam"

    def execute(self, context):
        found = detect.find_game()
        if not found:
            self.report({"WARNING"}, "Couldn't find the game; set its folder by hand")
            return {"CANCELLED"}
        game.preferences().game_path = str(found)
        self.report({"INFO"}, f"Game found in {found}")

        return {"FINISHED"}


CLASSES = (MT2_Preferences, MT2_OT_detect_paths)
