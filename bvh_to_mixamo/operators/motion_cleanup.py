"""Inspectable local cleanup; original source object and Action stay intact."""

from bpy.types import Operator

from ..core.animation_utils import pose_bone_selected
from ..core.motion_cleanup import audit_motion, cleanup_rotations, repair_root_gap
from .export_fbx import _get_export_armature
from .vmd_io import _save_report


class BVH_OT_audit_motion(Operator):
    bl_idname = "bvh.audit_motion"
    bl_label = "Inspect Motion"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            result = audit_motion(
                context, _get_export_armature(context), context.scene.frame_start, context.scene.frame_end
            )
            _save_report(result)
            frames = result["suspect_discontinuity_frames"]
            self.report(
                {"WARNING"} if frames else {"INFO"},
                "Root discontinuity candidates: " + str(frames[:12])
                if frames
                else "No large root steps in the export range. See Motion Report.",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class BVH_OT_cleanup_motion(Operator):
    bl_idname = "bvh.cleanup_motion"
    bl_label = "Create Denoised Copy"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        try:
            source = _get_export_armature(context)
            names = (
                [p.name for p in source.pose.bones if pose_bone_selected(p)]
                if scene.bvh_cleanup_selected_bones and source
                else None
            )
            if scene.bvh_cleanup_selected_bones and not names:
                raise ValueError("Select the rotation bones to clean first.")
            armature, result = cleanup_rotations(
                context,
                source,
                window_seconds=scene.bvh_cleanup_window,
                strength=scene.bvh_cleanup_strength,
                cap_degrees=scene.bvh_cleanup_cap,
                bone_names=names,
            )
            scene.bvh_last_output_armature = armature.name
            context.view_layer.objects.active = armature
            _save_report(result)
            self.report(
                {"INFO"},
                "Created a bounded rotation-cleanup copy. Translation and default-excluded fingers are retained.",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class BVH_OT_repair_root_gap(Operator):
    bl_idname = "bvh.repair_root_gap"
    bl_label = "Create Root Repair Copy"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        try:
            armature, result = repair_root_gap(
                context,
                _get_export_armature(context),
                scene.bvh_gap_start,
                scene.bvh_gap_end,
                confirmed=scene.bvh_gap_video_confirmed,
                root_name=scene.bvh_gap_root_bone or None,
            )
            scene.bvh_last_output_armature = armature.name
            context.view_layer.objects.active = armature
            armature.select_set(True)
            _save_report(result)
            self.report({"INFO"}, "Created a short root-gap repair copy. Review it against the source video.")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
