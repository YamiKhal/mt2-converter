import bpy

from . import game, pipeline, project
from .convert_out import asset_root
from .mt2model.naming import clean_word, mod_id_problem, model_path, target_problems


def _root(context):
    return asset_root(context.active_object)


class _AssetOperator(bpy.types.Operator):
    @classmethod
    def poll(cls, context):
        return _root(context) is not None


class MT2_OT_check(_AssetOperator):
    bl_idname = "mt2.check"
    bl_label = "Check"
    bl_description = "Build the model without writing it and list anything the game would reject"

    def execute(self, context):
        game.rescan()
        result = pipeline.plan(_root(context))
        pipeline.show(context.scene, result.root_obj, result.findings)
        errors = sum(f.level == "error" for f in result.findings)
        self.report({"WARNING"} if errors else {"INFO"},
                    f"{errors} error(s)" if errors else f"Ready: {result.rel}")

        return {"FINISHED"}


class MT2_OT_export(_AssetOperator):
    bl_idname = "mt2.export"
    bl_label = "Export"
    bl_description = "Check, then write the model and its data files into the mod folder"

    @classmethod
    def description(cls, context, properties):
        root = _root(context)
        target = pipeline.target_for(root) if root else None
        path = model_path(target) if target and not target_problems(target) else ""

        return f"Check, then write {path} and its data files into the mod folder" if path else cls.bl_description

    def execute(self, context):
        folder = game.project_dir()
        if folder is None or not folder.is_dir():
            self.report({"ERROR"}, "Choose the mod folder first")
            return {"CANCELLED"}
        game.rescan()
        result = pipeline.plan(_root(context))
        pipeline.show(context.scene, result.root_obj, result.findings)
        if not result.ok:
            self.report({"ERROR"}, "Not exported: fix the errors in the list")
            return {"CANCELLED"}
        written = pipeline.write(result)
        self.report({"INFO"}, "Wrote " + ", ".join(written))

        return {"FINISHED"}


class MT2_OT_forget_export(_AssetOperator):
    bl_idname = "mt2.forget_export"
    bl_label = "Forget previous export"
    bl_description = ("Allow this asset to export under a new path. The old file stays in the mod folder; "
                      "delete it yourself only if no player can have placed it")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        _root(context).mt2.exported_path = ""

        return {"FINISHED"}


class MT2_OT_select_finding(bpy.types.Operator):
    bl_idname = "mt2.select_finding"
    bl_label = "Select"
    bl_description = "Select the object this finding is about"

    index: bpy.props.IntProperty()

    def execute(self, context):
        item = context.scene.mt2.findings[self.index]
        obj = bpy.data.objects.get(item.object_name)
        if obj is None:
            return {"CANCELLED"}
        for other in context.selected_objects:
            other.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

        return {"FINISHED"}


class MT2_OT_setup(bpy.types.Operator):
    bl_idname = "mt2.setup"
    bl_label = "Set up"
    bl_description = "Point the tools at the game and at your mod's folder"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        row = layout.row(align=True)
        row.prop(game.preferences(), "game_path")
        row.operator("mt2.detect_paths", text="", icon="VIEWZOOM")
        settings = context.scene.mt2
        layout.prop(settings, "project_dir")
        row = layout.row(align=True)
        row.prop(settings, "mod_id")
        row.operator("mt2.load_project", text="", icon="FILE_REFRESH")
        folder = game.project_dir()
        if folder is not None and not (folder / project.MANIFEST).exists():
            layout.operator("mt2.create_project", icon="ADD")

    def execute(self, context):
        game.forget()

        return {"FINISHED"}


class MT2_OT_load_project(bpy.types.Operator):
    bl_idname = "mt2.load_project"
    bl_label = "Read manifest"
    bl_description = "Read the mod id from the mod folder's manifest.json"

    def execute(self, context):
        folder = game.project_dir()
        mod_id = project.read_mod_id(folder) if folder else None
        if not mod_id:
            self.report({"WARNING"}, "No manifest.json with an id in that folder")
            return {"CANCELLED"}
        context.scene.mt2.mod_id = mod_id
        game.forget()

        return {"FINISHED"}


class MT2_OT_create_project(bpy.types.Operator):
    bl_idname = "mt2.create_project"
    bl_label = "Create manifest"
    bl_description = "Write a manifest.json for the mod manager into the mod folder"

    mod_name: bpy.props.StringProperty(name="Mod name", default="My Models")
    author: bpy.props.StringProperty(name="Author")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        folder = game.project_dir()
        mod_id = context.scene.mt2.mod_id or clean_word(self.mod_name)
        problem = mod_id_problem(mod_id)
        if folder is None or problem:
            self.report({"ERROR"}, problem or "Choose the mod folder first")
            return {"CANCELLED"}
        if (folder / project.MANIFEST).exists():
            self.report({"ERROR"}, "That folder already has a manifest.json")
            return {"CANCELLED"}
        project.create_manifest(folder, mod_id, self.mod_name, self.author)
        context.scene.mt2.mod_id = mod_id

        return {"FINISHED"}


CLASSES = (MT2_OT_check, MT2_OT_export, MT2_OT_forget_export, MT2_OT_select_finding,
           MT2_OT_setup, MT2_OT_load_project, MT2_OT_create_project)
