import traceback

import bpy
from bpy.types import Operator

from ..core.armature_utils import get_selected_mixamo_armature, process_bones, verify_animation_data
from ..core.bone_mapping import get_active_bone_mapping, validate_skeleton_mapping
from ..core.bvh_parser import import_bvh
from ..core.export_profiles import export_armature_by_profile, resolve_export_profile
from ..core.i18n import LocalizedOperator, translated_report
from ..core.logger import log_error, log_info
from ..core.retarget_engine import transfer_animation
from ..core.template_loader import get_template_fbx_path, import_character_template_fbx
from ..core.ue5_profile import (
    TARGET_UE4_BASIC,
    TARGET_UE5_BASIC,
    convert_mixamo_armature_to_ue4_basic,
    convert_mixamo_armature_to_ue5_basic,
)
from ..core.vrm_profile import (
    TARGET_VRM_BODY,
    apply_vrm_leg_roll_180,
    get_vrm_body_target_to_source_mapping,
    validate_vrm_body_target,
)


class MIXAMO_OT_convert(LocalizedOperator, Operator):
    bl_idname = "mixamo.convert_bvh"
    bl_label = "Convert / Retarget BVH"
    bl_description = "Convert BVH motion to Mixamo, UE5, or VRM-compatible target rigs."
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        bvh_path = scene.bvh_input_path
        bind_mode = scene.bvh_bind_mode

        if not bvh_path:
            translated_report(context, self.report, {"ERROR"}, "Select a BVH source file first.")
            return {"CANCELLED"}
        if not bvh_path.lower().endswith(".bvh"):
            translated_report(context, self.report, {"ERROR"}, "Select a valid .bvh file.")
            return {"CANCELLED"}

        try:
            log_info("===== BVH Motion Retargeter: conversion started =====")
            target_armature = None
            imported_template_objects = []

            if bind_mode == "BIND_SELECTED":
                if scene.bvh_target_skeleton == TARGET_VRM_BODY:
                    selected_armatures = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
                    target_armature = selected_armatures[0] if selected_armatures else None
                    if not target_armature:
                        translated_report(
                            context, self.report, {"ERROR"}, "VRM retargeting requires a selected VRM Armature."
                        )
                        return {"CANCELLED"}
                else:
                    target_armature = get_selected_mixamo_armature()
                    if not target_armature:
                        translated_report(
                            context,
                            self.report,
                            {"ERROR"},
                            "Bind-to-selected mode requires a selected Mixamo-compatible armature.",
                        )
                        return {"CANCELLED"}
                log_info(f"Selected target armature: {target_armature.name}")

            try:
                bone_mapping = get_active_bone_mapping(context)
            except Exception as exc:
                translated_report(context, self.report, {"ERROR"}, f"Failed to load bone mapping JSON: {exc}")
                return {"CANCELLED"}

            source_armature, _bvh_fps = import_bvh(bvh_path, scene.bvh_match_fps)
            if not source_armature:
                translated_report(
                    context, self.report, {"ERROR"}, "BVH import failed. Check the file path and BVH format."
                )
                return {"CANCELLED"}

            source_report = validate_skeleton_mapping(source_armature, bone_mapping)
            if source_report["matched_count"] == 0:
                translated_report(
                    context,
                    self.report,
                    {"ERROR"},
                    "The selected mapping does not match the BVH skeleton. Check the preset or custom JSON.",
                )
                return {"CANCELLED"}
            if not source_report["can_continue"]:
                translated_report(
                    context,
                    self.report,
                    {"ERROR"},
                    f"Critical bone coverage is insufficient. Compatibility score {source_report['score']}/100",
                )
                return {"CANCELLED"}

            processed_armature = process_bones(source_armature, bone_mapping=bone_mapping, update_animation=True)
            if not verify_animation_data(processed_armature):
                translated_report(
                    context,
                    self.report,
                    {"WARNING"},
                    "Animation data may be incomplete. Please inspect the imported BVH.",
                )

            if bind_mode == "CREATE":
                if scene.bvh_target_skeleton in {TARGET_UE4_BASIC, TARGET_UE5_BASIC}:
                    processed_armature = (
                        convert_mixamo_armature_to_ue4_basic
                        if scene.bvh_target_skeleton == TARGET_UE4_BASIC
                        else convert_mixamo_armature_to_ue5_basic
                    )(
                        processed_armature,
                        root_motion_mode=scene.bvh_ue5_root_motion,
                        add_auxiliary_bones=scene.bvh_ue5_add_auxiliary_bones,
                    )
                elif scene.bvh_target_skeleton == TARGET_VRM_BODY:
                    translated_report(
                        context,
                        self.report,
                        {"ERROR"},
                        "VRM Humanoid Body requires binding to a selected/imported VRM armature; creating an empty VRM rig is not supported.",
                    )
                    return {"CANCELLED"}
                scene.bvh_last_output_armature = processed_armature.name
                if scene.bvh_auto_export_after_convert:
                    if not scene.bvh_export_path:
                        translated_report(
                            context, self.report, {"ERROR"}, "Auto export is enabled, but no FBX output path is set."
                        )
                        return {"CANCELLED"}
                    export_armature_by_profile(
                        processed_armature,
                        scene.bvh_export_path,
                        resolve_export_profile(scene),
                        include_mesh=scene.bvh_export_include_mesh,
                        overwrite=scene.bvh_export_overwrite,
                        allow_discontinuities=scene.bvh_export_allow_discontinuities,
                    )
                msg = f"Created target rig: {scene.bvh_target_skeleton} | Compatibility score {source_report['score']}/100"
                translated_report(context, self.report, {"INFO"}, msg)
                log_info("===== Conversion completed =====")
                return {"FINISHED"}

            if bind_mode == "BIND_TEMPLATE":
                try:
                    template_path = get_template_fbx_path(context)
                    target_armature, imported_template_objects = import_character_template_fbx(template_path)
                except Exception as exc:
                    translated_report(context, self.report, {"ERROR"}, f"Character template import failed: {exc}")
                    return {"CANCELLED"}

            target_to_source_mapping = None
            if scene.bvh_target_skeleton == TARGET_VRM_BODY:
                vrm_report = validate_vrm_body_target(target_armature)
                log_info(
                    f"VRM body mapping check: matched={vrm_report['matched_count']} missing={vrm_report['missing_count']} ignored_J_Sec={vrm_report['secondary_ignored_count']} score={vrm_report['score']}/100"
                )
                if not vrm_report["can_continue"]:
                    translated_report(
                        context,
                        self.report,
                        {"ERROR"},
                        "Missing critical VRM body bones: " + ", ".join(vrm_report["critical_missing"][:8]),
                    )
                    return {"CANCELLED"}
                if getattr(scene, "bvh_vrm_leg_roll_180", False):
                    roll_report = apply_vrm_leg_roll_180(
                        target_armature,
                        knee_compensation_left_degrees=getattr(scene, "bvh_vrm_knee_compensation_left", -45.0),
                        knee_compensation_right_degrees=getattr(scene, "bvh_vrm_knee_compensation_right", 45.0),
                    )
                    log_info(
                        "VRM thigh roll correction with independent knee compensation: changed="
                        + ", ".join(roll_report.get("changed", []))
                        + " knee="
                        + ", ".join(roll_report.get("knee_compensated", []))
                    )
                target_to_source_mapping = get_vrm_body_target_to_source_mapping()
            else:
                target_report = validate_skeleton_mapping(
                    processed_armature, {v: v for v in bone_mapping.values()}, target_armature=target_armature
                )
                if target_report["missing_target_count"] > 0:
                    translated_report(
                        context,
                        self.report,
                        {"WARNING"},
                        f"Target armature is missing some mapped bones; retarget quality may be affected: {target_report['missing_target_count']} bones",
                    )

            ok = transfer_animation(
                processed_armature,
                target_armature,
                root_motion_mode=scene.bvh_root_motion_mode,
                simplify_after_bake=scene.bvh_simplify_after_bake,
                simplify_factor=scene.bvh_simplify_factor,
                target_to_source_mapping=target_to_source_mapping,
            )
            if not ok:
                translated_report(context, self.report, {"ERROR"}, "Animation retargeting failed.")
                return {"CANCELLED"}

            if scene.bvh_target_skeleton in {TARGET_UE4_BASIC, TARGET_UE5_BASIC}:
                target_armature = (
                    convert_mixamo_armature_to_ue4_basic
                    if scene.bvh_target_skeleton == TARGET_UE4_BASIC
                    else convert_mixamo_armature_to_ue5_basic
                )(
                    target_armature,
                    root_motion_mode=scene.bvh_ue5_root_motion,
                    add_auxiliary_bones=scene.bvh_ue5_add_auxiliary_bones,
                )

            bpy.data.objects.remove(processed_armature, do_unlink=True)
            for obj in bpy.context.scene.objects:
                obj.select_set(False)
            if bind_mode == "BIND_TEMPLATE":
                for obj in imported_template_objects:
                    if obj and obj.name in bpy.data.objects:
                        obj.select_set(True)
            target_armature.select_set(True)
            bpy.context.view_layer.objects.active = target_armature

            scene.bvh_last_output_armature = target_armature.name
            if scene.bvh_auto_export_after_convert:
                if not scene.bvh_export_path:
                    translated_report(
                        context, self.report, {"ERROR"}, "Auto export is enabled, but no FBX output path is set."
                    )
                    return {"CANCELLED"}
                export_armature_by_profile(
                    target_armature,
                    scene.bvh_export_path,
                    resolve_export_profile(scene),
                    include_mesh=scene.bvh_export_include_mesh,
                    overwrite=scene.bvh_export_overwrite,
                    allow_discontinuities=scene.bvh_export_allow_discontinuities,
                )

            msg = f"BVH animation retargeted to {target_armature.name} | Target: {scene.bvh_target_skeleton} | Root: {scene.bvh_root_motion_mode}"
            translated_report(context, self.report, {"INFO"}, msg)
            log_info("===== Retargeting completed =====")
            return {"FINISHED"}

        except Exception as exc:
            log_error(f"Processing failed: {exc}")
            log_error(traceback.format_exc())
            translated_report(context, self.report, {"ERROR"}, f"Processing failed: {exc}")
            return {"CANCELLED"}
