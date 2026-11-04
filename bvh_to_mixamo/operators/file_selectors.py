from bpy.props import StringProperty
from bpy.types import Operator

from ..core.i18n import LocalizedOperator


class FILE_OT_select_bvh(LocalizedOperator, Operator):
    bl_idname = "file.select_bvh"
    bl_label = "Select BVH File"
    bl_description = "Select a BVH motion capture file."

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.bvh", options={"HIDDEN"})

    def execute(self, context):
        context.scene.bvh_input_path = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class FILE_OT_select_mapping_json(LocalizedOperator, Operator):
    bl_idname = "file.select_mapping_json"
    bl_label = "Select Mapping JSON"
    bl_description = "Select a custom BVH-to-Mixamo mapping JSON file."

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        context.scene.bvh_custom_mapping_path = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class FILE_OT_select_template_fbx(LocalizedOperator, Operator):
    bl_idname = "file.select_template_fbx"
    bl_label = "Select Character Template"
    bl_description = "Select a custom FBX, VRM, GLB, or GLTF character template."

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.fbx;*.vrm;*.glb;*.gltf", options={"HIDDEN"})

    def execute(self, context):
        context.scene.bvh_custom_template_fbx_path = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class FILE_OT_select_export_fbx(LocalizedOperator, Operator):
    bl_idname = "file.select_export_fbx"
    bl_label = "Select FBX Output Path"
    bl_description = "Select the FBX output file path for Mixamo or UE5 export."

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def execute(self, context):
        filepath = self.filepath
        if filepath and not filepath.lower().endswith(".fbx"):
            filepath += ".fbx"
        context.scene.bvh_export_path = filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
