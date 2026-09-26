import bpy

from . import game
from .anim_objects import NAME_KEY, import_animations, new_action, owned_actions
from .convert_out import asset_root
from .costume_objects import ACTOR_KEY
from .door_preview import is_door, play_door
from .rig_objects import rig_animations

ANIMATED_ASSETS = ("costume", "gizmo")


class _AnimatedOperator(bpy.types.Operator):
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and root.mt2.asset in ANIMATED_ASSETS


class MT2_OT_import_animations(_AnimatedOperator):
    bl_idname = "mt2.import_animations"
    bl_label = "Game animations"
    bl_description = "Load the game's animations for this costume's skeleton, to watch or to edit"

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and root.mt2.asset == "costume"

    def execute(self, context):
        root = asset_root(context.active_object)
        actor = root.get(ACTOR_KEY, "humanoid")
        if game.game_data() is None:
            self.report({"ERROR"}, "Set the game folder in the add-on preferences first")
            return {"CANCELLED"}
        found = rig_animations(actor)
        if not found:
            self.report({"ERROR"}, f"No animations found for '{actor}'")
            return {"CANCELLED"}
        loaded = {a.get(NAME_KEY) for a in owned_actions(root)}
        animations = [a for a in found if a.name not in loaded]
        actions = import_animations(root, animations)
        if actions:
            root.mt2.animation = actions[0].name
        self.report({"INFO"}, f"Loaded {len(actions)} animations")

        return {"FINISHED"}


class MT2_OT_new_animation(_AnimatedOperator):
    bl_idname = "mt2.new_animation"
    bl_label = "New animation"
    bl_description = ("Start an animation. Key the nodes or bones (I) on the timeline; "
                      "for characters, use a game name such as idle, run or attack_sword to replace it")

    name: bpy.props.StringProperty(name="Name", default="open")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        root = asset_root(context.active_object)
        if not self.name.strip():
            return {"CANCELLED"}
        action = new_action(root, self.name.strip())
        root.mt2.animation = action.name

        return {"FINISHED"}


class MT2_OT_play_door(_AnimatedOperator):
    bl_idname = "mt2.play_door"
    bl_label = "Play door"
    bl_description = ("Play unlock, open, close and open again in a row, the way the game plays a door, "
                      "to see parts that jump between them. Pick an animation again to edit it")

    @classmethod
    def poll(cls, context):
        root = asset_root(context.active_object)

        return root is not None and is_door(root)

    def execute(self, context):
        root = asset_root(context.active_object)
        action = play_door(root)
        root.mt2.animation = action.name
        if context.screen is not None and not context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()

        return {"FINISHED"}


CLASSES = (MT2_OT_import_animations, MT2_OT_new_animation, MT2_OT_play_door)
