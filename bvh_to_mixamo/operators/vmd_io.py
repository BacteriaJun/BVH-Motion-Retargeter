"""VMD customer workflow: import editable motion, refine, preserve/export."""

import json
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from ..core.armature_utils import ensure_object_mode
from ..core.mmd_mapping import mixamo_mapping
from ..core.vmd_blender import (
    SESSION_KEY,
    create_preview_armature,
    export_fk_motion,
    export_motion,
    import_motion,
    resolve_mapping,
)
from ..core.vmd_codec import read_vmd
from .export_fbx import _get_export_armature


def _save_report(value):
    text = bpy.data.texts.get("BVH_Last_Motion_Report") or bpy.data.texts.new("BVH_Last_Motion_Report")
    text.clear()
    text.write(json.dumps(value, ensure_ascii=False, indent=2))


class BVH_OT_import_vmd(Operator):
    bl_idname = "bvh.import_vmd"
    bl_label = "Import Editable VMD"
    bl_description = (
        "Import VMD to an FK reference or selected Japanese-named rig, retaining original sections for export."
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        path = bpy.path.abspath(scene.bvh_vmd_input_path)
        if not path or not Path(path).is_file() or Path(path).suffix.lower() != ".vmd":
            self.report({"ERROR"}, "Choose an existing .vmd source file.")
            return {"CANCELLED"}
        old_active = context.view_layer.objects.active
        old_selected = list(context.selected_objects)
        created = None
        try:
            # Parse invalid files before creating any reference rig.
            motion = read_vmd(path)
            ensure_object_mode()
            if scene.bvh_vmd_import_mode == "PREVIEW":
                created = create_preview_armature(context, motion, unit_scale=scene.bvh_vmd_unit_scale)
                armature = created
            else:
                armature = context.view_layer.objects.active
                if not armature or armature.type != "ARMATURE":
                    raise ValueError("Select the target MMD armature first, or choose Reference Preview.")
            report = import_motion(
                context,
                path,
                armature,
                unit_scale=scene.bvh_vmd_unit_scale,
                frame_start=scene.bvh_vmd_frame_start,
                match_fps=scene.bvh_vmd_match_fps,
            )
            scene.bvh_last_output_armature = armature.name
            context.view_layer.objects.active = armature
            armature.select_set(True)
            _save_report(report)
            self.report(
                {"INFO"},
                f"VMD imported: {report['mapped_bones']} editable bone tracks. Original extra tracks retained.",
            )
            return {"FINISHED"}
        except Exception as exc:
            if created is not None:
                data = created.data
                bpy.data.objects.remove(created, do_unlink=True)
                if data.users == 0:
                    bpy.data.armatures.remove(data)
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in old_selected:
                obj.select_set(True)
            context.view_layer.objects.active = old_active
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class BVH_OT_export_vmd(Operator):
    bl_idname = "bvh.export_vmd"
    bl_label = "Export VMD"
    bl_description = "Preserve the imported VMD sections, or explicitly create a new mapped FK motion."
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        armature = _get_export_armature(context)
        path = bpy.path.abspath(scene.bvh_vmd_output_path)
        try:
            if not armature or not path or Path(path).suffix.lower() != ".vmd":
                raise ValueError("Select a motion armature and a .vmd output path.")
            if scene.bvh_vmd_export_mode == "PRESERVE":
                if SESSION_KEY not in armature:
                    raise ValueError(
                        "Preserve mode needs an imported VMD session. Choose New FK for BVH/Mixamo motion."
                    )
                report = export_motion(context, path, armature, overwrite=scene.bvh_export_overwrite)
            else:
                mapping = (
                    mixamo_mapping(armature, scene.bvh_vmd_finger_digits)
                    if scene.bvh_vmd_fk_mapping == "MIXAMO"
                    else None
                )
                if mapping is None:
                    mapping = resolve_mapping(armature)
                scale = scene.bvh_vmd_unit_scale
                if scene.bvh_vmd_reference_scale:
                    from ..core.motion_cleanup import leg_length

                    scale = leg_length(armature) / (math_sqrt(4**2 + 0.25**2) + math_sqrt(4.2**2 + 0.25**2))
                from ..core.export_profiles import export_preflight

                export_preflight(context, armature, scene.bvh_export_allow_discontinuities)
                report = export_fk_motion(
                    context, path, armature, mapping, unit_scale=scale, overwrite=scene.bvh_export_overwrite
                )
            _save_report(report)
            self.report({"INFO"}, "VMD exported. See the motion report for retained tracks and FK limits.")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


def math_sqrt(value):
    return value**0.5


class FILE_OT_select_vmd_input(Operator):
    bl_idname = "file.select_vmd_input"
    bl_label = "Select VMD Source"
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.vmd", options={"HIDDEN"})

    def execute(self, context):
        context.scene.bvh_vmd_input_path = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class FILE_OT_select_vmd_output(Operator):
    bl_idname = "file.select_vmd_output"
    bl_label = "Select VMD Output"
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.vmd", options={"HIDDEN"})

    def execute(self, context):
        context.scene.bvh_vmd_output_path = (
            self.filepath if self.filepath.lower().endswith(".vmd") else self.filepath + ".vmd"
        )
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
