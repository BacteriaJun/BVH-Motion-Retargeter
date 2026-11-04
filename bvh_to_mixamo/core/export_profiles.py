"""Named FBX workflows with explicit sampling, preflight and atomic file writes."""

import math
import os
import tempfile
from pathlib import Path

import bpy

from .animation_utils import iter_action_fcurves
from .armature_utils import ensure_object_mode
from .logger import log_info, log_warning
from .motion_cleanup import audit_motion
from .ue5_profile import TARGET_UE4_BASIC, TARGET_UE5_BASIC, get_armature_meshes

EXPORT_PROFILE_AUTO = "AUTO"
EXPORT_PROFILE_MIXAMO = "MIXAMO_FBX"
EXPORT_PROFILE_UE4 = "UE4_FBX"
EXPORT_PROFILE_UE5 = "UE5_FBX"


def _normalize_fbx_path(filepath):
    if not filepath:
        raise ValueError("Set an FBX output path first.")
    path = os.path.abspath(os.path.expanduser(bpy.path.abspath(str(filepath))))
    return path if path.lower().endswith(".fbx") else path + ".fbx"


def resolve_export_profile(scene):
    profile = getattr(scene, "bvh_export_profile", EXPORT_PROFILE_AUTO)
    if profile == EXPORT_PROFILE_AUTO:
        return {TARGET_UE5_BASIC: EXPORT_PROFILE_UE5, TARGET_UE4_BASIC: EXPORT_PROFILE_UE4}.get(
            scene.bvh_target_skeleton, EXPORT_PROFILE_MIXAMO
        )
    return profile


def select_export_set(armature, include_mesh=True):
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    if include_mesh:
        for mesh in get_armature_meshes(armature):
            mesh.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature


def export_preflight(context, armature, allow_discontinuities=False):
    if not armature or armature.type != "ARMATURE":
        raise ValueError("Select an armature before exporting.")
    if not armature.animation_data or not armature.animation_data.action:
        raise ValueError("No active motion Action to export.")
    scene = context.scene
    previous = scene.frame_current
    subframe = scene.frame_subframe
    try:
        for frame in range(scene.frame_start, scene.frame_end + 1):
            for curve in iter_action_fcurves(armature.animation_data.action, armature):
                if not curve.mute and not math.isfinite(curve.evaluate(frame)):
                    raise ValueError(f"Non-finite animation value at frame {frame}: {curve.data_path}")
    finally:
        scene.frame_set(previous, subframe=subframe)
    report = audit_motion(context, armature, scene.frame_start, scene.frame_end)
    if report["severe_discontinuity_frames"] and not allow_discontinuities:
        frames = ", ".join(str(x) for x in report["severe_discontinuity_frames"][:12])
        raise ValueError(
            f"Large root discontinuities at frames {frames}. Review/trim the export range, or explicitly allow discontinuities."
        )
    if report["suspect_discontinuity_frames"]:
        log_warning("Review root discontinuity candidates: " + str(report["suspect_discontinuity_frames"][:12]))
    return report


def _export(armature, filepath, profile, include_mesh=True, overwrite=False, allow_discontinuities=False):
    path = Path(_normalize_fbx_path(filepath))
    if path.exists() and not overwrite:
        raise FileExistsError("Output exists. Choose a new name or enable overwrite explicitly.")
    if not path.parent.is_dir():
        raise ValueError("The output directory does not exist.")
    context = bpy.context
    export_preflight(context, armature, allow_discontinuities)
    if profile in {EXPORT_PROFILE_UE4, EXPORT_PROFILE_UE5}:
        required = {"root", "pelvis", "thigh_l", "thigh_r", "foot_l", "foot_r"}
        if not required.issubset(armature.data.bones.keys()):
            raise ValueError("Create/retarget an Unreal humanoid profile before using the UE FBX preset.")
        if armature.data.bones["root"].parent:
            raise ValueError("Unreal root must be a top-level bone.")
    original_frame = context.scene.frame_current
    original_subframe = context.scene.frame_subframe
    active = context.view_layer.objects.active
    selected = list(context.selected_objects)
    previous_mode = context.object.mode if context.object else "OBJECT"
    fd, temp = tempfile.mkstemp(prefix=".bvh-export-", suffix=".fbx", dir=path.parent)
    os.close(fd)
    try:
        ensure_object_mode()
        select_export_set(armature, include_mesh)
        result = bpy.ops.export_scene.fbx(
            filepath=temp,
            use_selection=True,
            object_types={"ARMATURE", "MESH"} if include_mesh else {"ARMATURE"},
            axis_forward="-Z",
            axis_up="Y",
            add_leaf_bones=False,
            use_armature_deform_only=False,
            bake_anim=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True,
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_UNITS",
            use_space_transform=True,
            primary_bone_axis="Y",
            secondary_bone_axis="X",
            armature_nodetype="NULL",
        )
        if result != {"FINISHED"} or Path(temp).stat().st_size < 64:
            raise RuntimeError("Blender did not finish the FBX export.")
        if overwrite:
            os.replace(temp, path)
        else:
            os.link(temp, path)
            os.unlink(temp)
        log_info(f"{profile} exported: {path}")
        return str(path)
    finally:
        context.scene.frame_set(original_frame, subframe=original_subframe)
        if os.path.exists(temp):
            os.unlink(temp)
        ensure_object_mode()
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in selected:
            if obj.name in context.view_layer.objects:
                obj.select_set(True)
        if active and active.name in context.view_layer.objects:
            context.view_layer.objects.active = active
            if previous_mode in {"POSE", "EDIT"}:
                bpy.ops.object.mode_set(mode=previous_mode)


def export_armature_to_mixamo_fbx(armature, filepath, include_mesh=True, overwrite=False, allow_discontinuities=False):
    return _export(armature, filepath, EXPORT_PROFILE_MIXAMO, include_mesh, overwrite, allow_discontinuities)


def export_armature_to_ue5_fbx(armature, filepath, include_mesh=True, overwrite=False, allow_discontinuities=False):
    return _export(armature, filepath, EXPORT_PROFILE_UE5, include_mesh, overwrite, allow_discontinuities)


def export_armature_by_profile(
    armature, filepath, profile, include_mesh=True, overwrite=False, allow_discontinuities=False
):
    if profile not in {EXPORT_PROFILE_MIXAMO, EXPORT_PROFILE_UE4, EXPORT_PROFILE_UE5}:
        raise ValueError(f"Unknown FBX profile: {profile}")
    return _export(armature, filepath, profile, include_mesh, overwrite, allow_discontinuities)
