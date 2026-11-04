"""Non-destructive, bounded Action cleanup for BVH and imported FK VMD.

No surface/world anchor is inferred. The caller explicitly confirms short root
packet repairs. Missing-end tails are diagnosed rather than extrapolated.
"""

import math

import bpy
from mathutils import Euler, Quaternion

from .animation_utils import action_fcurve_collection, iter_action_fcurves
from .motion_math import denoise_quaternions, reconstruct_short_gap

LEG_CHAINS = [
    ("mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot"),
    ("mixamorig:RightUpLeg", "mixamorig:RightLeg", "mixamorig:RightFoot"),
    ("LeftUpLeg", "LeftLeg", "LeftFoot"),
    ("RightUpLeg", "RightLeg", "RightFoot"),
    ("thigh_l", "calf_l", "foot_l"),
    ("thigh_r", "calf_r", "foot_r"),
    ("左足", "左ひざ", "左足首"),
    ("右足", "右ひざ", "右足首"),
]
ROOT_NAMES = ("センター", "mixamorig:Hips", "Hips", "pelvis", "root", "全ての親")
FINGER_MARKERS = (
    "thumb",
    "index",
    "middle",
    "ring",
    "pinky",
    "finger",
    "親指",
    "人指",
    "人差",
    "中指",
    "薬指",
    "小指",
    "目",
    "eye",
    "ik",
    "ｉｋ",
)


def _source(armature):
    if not armature or armature.type != "ARMATURE" or not armature.animation_data or not armature.animation_data.action:
        raise ValueError("Select an armature with an active Action.")
    return armature.animation_data.action


def _range(armature):
    action = _source(armature)
    start, end = math.ceil(action.frame_range[0]), math.floor(action.frame_range[1])
    if end < start or end - start + 1 > 100_000:
        raise ValueError("Cleanup requires 1–100,000 sampled frames in the active Action.")
    return start, end


def leg_length(armature):
    lengths = []
    for a, b, c in LEG_CHAINS:
        bones = armature.data.bones
        if all(n in bones for n in (a, b, c)):
            lengths.append(
                (bones[a].head_local - bones[b].head_local).length + (bones[b].head_local - bones[c].head_local).length
            )
    value = sum(lengths) / len(lengths) if lengths else 0.0
    if value <= 1e-8:
        raise ValueError("A recognized thigh/knee/ankle chain is needed for scale-aware checks.")
    return value


def audit_motion(context, armature, start=None, end=None):
    _source(armature)
    a, z = _range(armature)
    a = a if start is None else max(a, int(start))
    z = z if end is None else min(z, int(end))
    if z < a:
        raise ValueError("The requested range does not overlap the active Action.")
    L = leg_length(armature)
    root = next((armature.pose.bones[n] for n in ROOT_NAMES if n in armature.pose.bones), None)
    if root is None:
        root = next((b for b in armature.pose.bones if b.parent is None), None)
    if root is None:
        raise ValueError("Armature has no root bone.")
    original = context.scene.frame_current
    original_subframe = context.scene.frame_subframe
    points = []
    object_scale = None
    try:
        for frame in range(a, z + 1):
            context.scene.frame_set(frame)
            scale = armature.matrix_world.to_scale()
            if min(scale) <= 1e-8 or max(scale) - min(scale) > 1e-5 * max(scale):
                raise ValueError("Motion audit requires a positive uniform object scale. Apply/bake scale first.")
            if object_scale is None:
                object_scale = scale.x
            elif abs(scale.x - object_scale) > 1e-5 * object_scale:
                raise ValueError("Bake animated object scale before motion audit/export.")
            for pose in armature.pose.bones:
                if not all(math.isfinite(v) for row in pose.matrix for v in row):
                    raise ValueError(f"Non-finite bone transform at frame {frame}: {pose.name}")
            p = tuple(armature.matrix_world @ root.head)
            if not all(math.isfinite(v) for v in p):
                raise ValueError(f"Non-finite root at frame {frame}.")
            points.append(p)
    finally:
        context.scene.frame_set(original, subframe=original_subframe)
    L *= object_scale or 1.0
    steps = [math.dist(x, y) / L for x, y in zip(points, points[1:])]
    suspect = [a + i + 1 for i, v in enumerate(steps) if v > 0.25]
    severe = [a + i + 1 for i, v in enumerate(steps) if v > 1.0]
    return {
        "source_action": armature.animation_data.action.name,
        "root_bone": root.name,
        "frame_range": [a, z],
        "leg_length_world_units": L,
        "root_space": "world_including_object_motion",
        "max_root_step_L": max(steps, default=0.0),
        "suspect_discontinuity_frames": suspect,
        "severe_discontinuity_frames": severe,
        "scope": "Root-motion steps in the selected range, normalized by leg length.",
    }


def _copy_for_edit(context, armature, suffix):
    source = _source(armature)
    if armature.animation_data.nla_tracks and any(not t.mute for t in armature.animation_data.nla_tracks):
        raise ValueError("Bake or mute NLA tracks before Action cleanup.")
    if armature.animation_data.drivers:
        raise ValueError("Bake drivers before Action cleanup.")
    if armature.constraints or any(p.constraints for p in armature.pose.bones):
        raise ValueError("Bake constraints before FK Action cleanup; the original rig is preserved.")
    copied = armature.copy()
    copied.data = armature.data.copy()
    copied.name = armature.name + suffix
    copied.animation_data.action = source.copy()
    copied.animation_data.action.name = source.name + suffix
    context.collection.objects.link(copied)
    # Existing VMD sidecar properties are copied, retaining untouched sections.
    copied["bvh_cleanup_source_action"] = source.name
    copied["bvh_cleanup_quality"] = "bounded_rotation_cleanup"
    return copied


def _discard(copied):
    data = copied.data
    action = copied.animation_data.action if copied.animation_data else None
    bpy.data.objects.remove(copied, do_unlink=True)
    if data.users == 0:
        bpy.data.armatures.remove(data)
    if action and action.users == 0:
        bpy.data.actions.remove(action)


def _key_rotation(pose, quaternion, frame, previous_euler=None):
    q = Quaternion(quaternion)
    if pose.rotation_mode == "QUATERNION":
        pose.rotation_quaternion = q
        pose.keyframe_insert("rotation_quaternion", frame=frame, group=pose.name)
        return previous_euler
    if pose.rotation_mode == "AXIS_ANGLE":
        axis, angle = q.to_axis_angle()
        pose.rotation_axis_angle = (angle, *axis)
        pose.keyframe_insert("rotation_axis_angle", frame=frame, group=pose.name)
        return previous_euler
    euler = (
        q.to_euler(pose.rotation_mode, previous_euler) if previous_euler is not None else q.to_euler(pose.rotation_mode)
    )
    pose.rotation_euler = euler
    pose.keyframe_insert("rotation_euler", frame=frame, group=pose.name)
    return euler


def cleanup_rotations(context, armature, window_seconds=0.12, strength=0.5, cap_degrees=3.0, bone_names=None):
    _source(armature)
    a, z = _range(armature)
    fps = context.scene.render.fps / context.scene.render.fps_base
    names = (
        list(bone_names)
        if bone_names
        else [p.name for p in armature.pose.bones if not any(m in p.name.lower() for m in FINGER_MARKERS)]
    )
    if not names or any(n not in armature.pose.bones for n in names):
        raise ValueError("Select valid rotation bones to clean.")
    if (z - a + 1) * len(names) > 1_000_000:
        raise ValueError("Cleanup exceeds the one-million bone-sample budget. Limit the Action or selected bones.")
    current = context.scene.frame_current
    subframe = context.scene.frame_subframe
    old_active = context.view_layer.objects.active
    copied = None
    values = {n: [] for n in names}
    eulers = {n: [] for n in names}
    try:
        for frame in range(a, z + 1):
            context.scene.frame_set(frame)
            for n in names:
                values[n].append(tuple(armature.pose.bones[n].matrix_basis.to_quaternion()))
                eulers[n].append(tuple(armature.pose.bones[n].rotation_euler))
        # Protect source root discontinuities from being bridged by smoothing.
        try:
            audit = audit_motion(context, armature)
            protected = [
                any(abs(frame - c) <= 3 for c in audit["suspect_discontinuity_frames"]) for frame in range(a, z + 1)
            ]
        except ValueError:
            audit = None
            protected = [False] * (z - a + 1)
        filtered = {}
        reports = {}
        for n in names:
            filtered[n], reports[n] = denoise_quaternions(
                values[n], fps, window_seconds, strength, cap_degrees, protected
            )
        copied = _copy_for_edit(context, armature, "_Denoised")
        collection = action_fcurve_collection(copied.animation_data.action, copied)
        changed_curve_count = 0
        for n in names:
            mode = copied.pose.bones[n].rotation_mode
            prop = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}.get(
                mode, "rotation_euler"
            )
            updates = {}
            for i, frame in enumerate(range(a, z + 1)):
                if (
                    not reports[n]["changed_samples"]
                    or abs(sum(x * y for x, y in zip(filtered[n][i], values[n][i]))) >= 1 - 1e-14
                ):
                    continue
                q = Quaternion(filtered[n][i])
                if mode == "QUATERNION":
                    value = tuple(q)
                elif mode == "AXIS_ANGLE":
                    axis, angle = q.to_axis_angle()
                    value = (angle, *axis)
                else:
                    value = tuple(q.to_euler(mode, Euler(eulers[n][i], mode)))
                updates[frame] = value
            if not updates:
                continue
            path = copied.pose.bones[n].path_from_id(prop)
            count = 4 if mode in {"QUATERNION", "AXIS_ANGLE"} else 3
            for component in range(count):
                fc = next((f for f in collection if f.data_path == path and f.array_index == component), None)
                if fc is None:
                    try:
                        fc = collection.new(data_path=path, index=component, action_group=n)
                    except TypeError:
                        fc = collection.new(data_path=path, index=component, group_name=n)
                existing = {float(k.co.x): k for k in fc.keyframe_points}
                missing = []
                # Never hold old RNA key pointers while resizing the collection.
                for frame, value in updates.items():
                    key = existing.get(float(frame))
                    if key is None:
                        missing.append((frame, value[component]))
                    else:
                        key.co.y = value[component]
                        key.interpolation = "LINEAR"
                del existing
                for frame, value in missing:
                    key = fc.keyframe_points.insert(frame, value, options={"FAST"})
                    key.interpolation = "LINEAR"
                fc.update()
                changed_curve_count += 1
        copied["bvh_cleanup_max_angle_degrees"] = max(
            (r["max_correction_degrees"] for r in reports.values()), default=0.0
        )
        context.view_layer.objects.active = copied
        copied.select_set(True)
        return copied, {
            "method": "bounded_SO3_quadratic",
            "curve_write_mode": "batched_values_and_FAST_sparse_insert",
            "changed_curve_count": changed_curve_count,
            "frame_range": [a, z],
            "bone_reports": reports,
            "source_action_unchanged": True,
            "root_translation_unchanged": True,
            "fingers_excluded_by_default": bone_names is None,
            "source_audit": audit,
            "max_correction_degrees": copied["bvh_cleanup_max_angle_degrees"],
        }
    except Exception:
        if copied is not None:
            _discard(copied)
        context.view_layer.objects.active = old_active
        raise
    finally:
        context.scene.frame_set(current, subframe=subframe)


def repair_root_gap(context, armature, start_frame, end_frame, confirmed=False, root_name=None, cap_L=0.3):
    a, z = _range(armature)
    object_channels = {"location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"}
    if any(fc.data_path in object_channels for fc in iter_action_fcurves(armature.animation_data.action, armature)):
        raise ValueError("This repair edits a pose root bone. Bake animated object motion into root channels first.")
    name = root_name or next((n for n in ROOT_NAMES if n in armature.pose.bones), None)
    if name not in armature.pose.bones:
        raise ValueError("Choose the root translation bone.")
    current = context.scene.frame_current
    subframe = context.scene.frame_subframe
    copied = None
    try:
        positions = []
        for frame in range(a, z + 1):
            context.scene.frame_set(frame)
            positions.append(tuple(armature.pose.bones[name].location))
        # Pose location is expressed in a rigid rest basis, preserving its norm.
        out, report = reconstruct_short_gap(
            positions,
            context.scene.render.fps / context.scene.render.fps_base,
            start_frame - a,
            end_frame - a,
            leg_length(armature),
            confirmed,
            cap_L,
        )
        copied = _copy_for_edit(context, armature, "_RootRepair")
        for frame in range(start_frame, end_frame + 1):
            copied.pose.bones[name].location = out[frame - a]
            copied.pose.bones[name].keyframe_insert("location", frame=frame, group=name)
        return copied, {**report, "frame_range": [start_frame, end_frame], "source_action_unchanged": True}
    except Exception:
        if copied is not None:
            _discard(copied)
        raise
    finally:
        context.scene.frame_set(current, subframe=subframe)
