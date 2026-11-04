import traceback

import bpy

from .animation_utils import iter_action_fcurves
from .armature_utils import calculate_motion_scale, ensure_object_mode
from .logger import log_error, log_info

ROOT_KEEP = "KEEP"
ROOT_IN_PLACE = "IN_PLACE"
ROOT_SCALE = "SCALE"
RETARGET_CONSTRAINT = "CONSTRAINT_BAKE"

LIMB_KEYWORDS = (
    "LeftArm",
    "LeftForeArm",
    "LeftHand",
    "RightArm",
    "RightForeArm",
    "RightHand",
    "LeftUpLeg",
    "LeftLeg",
    "LeftFoot",
    "RightUpLeg",
    "RightLeg",
    "RightFoot",
    "UpperArm",
    "LowerArm",
    "Hand",
    "UpperLeg",
    "LowerLeg",
    "Foot",
)


def estimate_chain_length(armature, chain):
    total = 0.0
    for bone_name in chain:
        bone = armature.data.bones.get(bone_name) if armature else None
        if not bone:
            return 0.0
        total += bone.length
    return total


def calculate_motion_scale_for_mapping(source_armature, target_armature, target_to_source_mapping=None):
    """Calculate scale for same-name Mixamo or mapped target rigs.

    When target_to_source_mapping is provided, keys are target bone names and
    values are source Mixamo bone names. This is used by the VRM body-only
    profile where the target keeps J_Bip_* names.
    """
    if not target_to_source_mapping:
        return calculate_motion_scale(source_armature, target_armature)
    source_to_target = {src: tgt for tgt, src in target_to_source_mapping.items()}
    source_chains = [
        ("mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot"),
        ("mixamorig:RightUpLeg", "mixamorig:RightLeg", "mixamorig:RightFoot"),
    ]
    ratios = []
    for source_chain in source_chains:
        target_chain = tuple(source_to_target.get(name, "") for name in source_chain)
        source_len = estimate_chain_length(source_armature, source_chain)
        target_len = estimate_chain_length(target_armature, target_chain)
        if source_len > 0 and target_len > 0:
            ratios.append(target_len / source_len)
    if ratios:
        ratio = sum(ratios) / len(ratios)
        log_info(f"Motion Scale按映射腿长计算: ratio={ratio:.4f}")
        return ratio
    log_info("映射腿长不可用，回退到同名Mixamo比例计算")
    return calculate_motion_scale(source_armature, target_armature)


def get_action_frame_range(armature):
    action = armature.animation_data.action if armature.animation_data else None
    if action:
        return int(action.frame_range[0]), int(action.frame_range[1])
    return bpy.context.scene.frame_start, bpy.context.scene.frame_end


def _pose_bone_selected(pose_bone):
    return pose_bone.select if hasattr(pose_bone, "select") else pose_bone.bone.select


def _set_pose_bone_selected(pose_bone, selected):
    if hasattr(pose_bone, "select"):
        pose_bone.select = selected
    else:
        pose_bone.bone.select = selected


def _capture_pose(armature):
    return {
        p.name: {
            "rotation_mode": p.rotation_mode,
            "location": tuple(p.location),
            "rotation_euler": tuple(p.rotation_euler),
            "rotation_quaternion": tuple(p.rotation_quaternion),
            "rotation_axis_angle": tuple(p.rotation_axis_angle),
            "scale": tuple(p.scale),
            "selected": _pose_bone_selected(p),
        }
        for p in armature.pose.bones
    }


def _restore_pose(armature, states):
    for name, state in states.items():
        pose = armature.pose.bones.get(name)
        if pose is not None:
            pose.rotation_mode = state["rotation_mode"]
            for field in ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"):
                setattr(pose, field, state[field])


def clear_pose_constraints(armature):
    if not armature or armature.type != "ARMATURE":
        return
    for pose_bone in armature.pose.bones:
        for constraint in list(pose_bone.constraints):
            pose_bone.constraints.remove(constraint)


def transfer_animation_with_constraints(
    source_armature, target_armature, root_motion_mode=ROOT_SCALE, target_to_source_mapping=None
):
    log_info("使用稳定Constraint Bake兼容模式转移动画")
    if (
        not source_armature
        or not target_armature
        or source_armature.type != "ARMATURE"
        or target_armature.type != "ARMATURE"
        or source_armature == target_armature
    ):
        log_error("Retargeting requires two different armature objects.")
        return False
    if not source_armature.animation_data or not source_armature.animation_data.action:
        log_error("源骨骼没有动画数据")
        return False

    if target_armature.constraints or any(b.constraints for b in target_armature.pose.bones):
        log_error("Bake or duplicate a constraint-driven target rig before FK Constraint Bake retargeting.")
        return False
    if target_armature.animation_data and (
        target_armature.animation_data.drivers or any(not t.mute for t in target_armature.animation_data.nla_tracks)
    ):
        log_error("Bake/mute the target NLA and drivers before FK Constraint Bake retargeting.")
        return False
    original_target_action = target_armature.animation_data.action if target_armature.animation_data else None
    original_fake_user = original_target_action.use_fake_user if original_target_action else False
    original_target_had_animation_data = target_armature.animation_data is not None
    original_target_slot = getattr(target_armature.animation_data, "action_slot", None)
    original_target_pose = _capture_pose(target_armature)
    original_actions = set(bpy.data.actions)
    temporary_constraints = []
    completed = False
    original_subframe = bpy.context.scene.frame_subframe
    original_frame = bpy.context.scene.frame_current
    original_active = bpy.context.view_layer.objects.active
    original_mode = original_active.mode if original_active else "OBJECT"
    original_selected = list(bpy.context.selected_objects)
    original_scale = source_armature.scale.copy()
    source_original_pos = source_armature.location.copy()
    frame_start, frame_end = get_action_frame_range(source_armature)

    try:
        ensure_object_mode()
        scale_ratio = (
            calculate_motion_scale_for_mapping(source_armature, target_armature, target_to_source_mapping)
            if root_motion_mode == ROOT_SCALE
            else 1.0
        )
        source_armature.scale = (scale_ratio, scale_ratio, scale_ratio)
        source_armature.location = target_armature.location.copy()
        bpy.context.view_layer.update()

        if not target_armature.animation_data:
            target_armature.animation_data_create()
        if target_armature.animation_data.action:
            target_armature.animation_data.action.use_fake_user = True
            target_armature.animation_data.action = None

        bpy.context.view_layer.objects.active = target_armature
        ensure_object_mode()
        bpy.ops.object.mode_set(mode="POSE")
        clear_pose_constraints(target_armature)

        added = 0
        for pose_bone in target_armature.pose.bones:
            target_bone_name = pose_bone.name
            source_bone_name = (
                target_to_source_mapping.get(target_bone_name, target_bone_name)
                if target_to_source_mapping
                else target_bone_name
            )
            if source_bone_name not in source_armature.pose.bones:
                continue
            if source_bone_name == "mixamorig:Hips" and root_motion_mode != ROOT_IN_PLACE:
                loc = pose_bone.constraints.new("COPY_LOCATION")
                loc.target = source_armature
                loc.subtarget = source_bone_name
                loc.target_space = "LOCAL"
                loc.owner_space = "LOCAL"
                temporary_constraints.append((pose_bone.name, loc.name))
            rot = pose_bone.constraints.new("COPY_ROTATION")
            rot.target = source_armature
            rot.subtarget = source_bone_name
            is_limb = any((key in source_bone_name) or (key in target_bone_name) for key in LIMB_KEYWORDS)
            rot.target_space = "POSE" if is_limb else "LOCAL"
            rot.owner_space = "POSE" if is_limb else "LOCAL"
            temporary_constraints.append((pose_bone.name, rot.name))
            added += 1
        log_info(f"添加了 {added} 个骨骼约束")
        if added == 0:
            raise ValueError("No source bones match the target mapping.")

        ensure_object_mode()
        bpy.context.view_layer.objects.active = target_armature
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        target_armature.select_set(True)
        source_armature.select_set(False)
        bpy.ops.object.mode_set(mode="POSE")
        for pose_bone in target_armature.pose.bones:
            _set_pose_bone_selected(pose_bone, True)
        log_info(f"开始烘焙动画: {frame_start} - {frame_end}")
        result = bpy.ops.nla.bake(
            frame_start=frame_start,
            frame_end=frame_end,
            only_selected=True,
            visual_keying=True,
            clear_constraints=True,
            clear_parents=False,
            use_current_action=False,
            bake_types={"POSE"},
        )
        if result != {"FINISHED"}:
            raise RuntimeError("Blender did not finish NLA baking.")
        clear_pose_constraints(target_armature)
        ensure_object_mode()
        completed = bool(target_armature.animation_data and target_armature.animation_data.action)
        return completed
    except Exception as exc:
        log_error(f"Constraint Bake动画转移失败: {exc}")
        log_error(traceback.format_exc())
        return False
    finally:
        ensure_object_mode()
        # The bake may fail after clearing only some constraints. Remove only
        # the temporary constraints created in this call, never a user rig.
        for bone_name, constraint_name in temporary_constraints:
            pose = target_armature.pose.bones.get(bone_name)
            constraint = pose.constraints.get(constraint_name) if pose else None
            if constraint is not None:
                pose.constraints.remove(constraint)
        if not completed and target_armature.animation_data:
            target_armature.animation_data.action = original_target_action
            if original_target_slot is not None and hasattr(target_armature.animation_data, "action_slot"):
                target_armature.animation_data.action_slot = original_target_slot
            if original_target_action:
                original_target_action.use_fake_user = original_fake_user
            if not original_target_had_animation_data:
                target_armature.animation_data_clear()
        if not completed:
            _restore_pose(target_armature, original_target_pose)
            for action in list(bpy.data.actions):
                if action not in original_actions and action.users == 0 and not action.use_fake_user:
                    bpy.data.actions.remove(action)
        source_armature.scale = original_scale
        source_armature.location = source_original_pos
        bpy.context.scene.frame_set(original_frame, subframe=original_subframe)
        for name, state in original_target_pose.items():
            pose = target_armature.pose.bones.get(name)
            if pose is not None:
                _set_pose_bone_selected(pose, state["selected"])
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for obj in original_selected:
            if obj.name in bpy.context.view_layer.objects:
                obj.select_set(True)
        if original_active and original_active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = original_active
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=original_mode)


def simplify_fcurves(armature, factor=0.01):
    """Reduce only linear baked channels, preserving a named original take."""
    from .motion_math import reduce_linear_points

    if not armature.animation_data or not armature.animation_data.action:
        return
    source = armature.animation_data.action
    proposals = []
    for fc in iter_action_fcurves(source, armature):
        points = [(float(k.co.x), float(k.co.y)) for k in fc.keyframe_points]
        if fc.modifiers or any(k.interpolation != "LINEAR" for k in fc.keyframe_points):
            continue
        ids, _ = reduce_linear_points(points, factor)
        if len(ids) < len(points):
            proposals.append((fc.data_path, fc.array_index, [points[i] for i in ids]))
    if not proposals:
        log_info("No eligible linear baked curves needed key reduction. Bezier curves remain intact.")
        return
    source.use_fake_user = True
    reduced = source.copy()
    reduced.name = source.name + "_Reduced"
    armature.animation_data.action = reduced
    for path, index, points in proposals:
        fc = next(f for f in iter_action_fcurves(reduced, armature) if f.data_path == path and f.array_index == index)
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(points))
        for key, (frame, value) in zip(fc.keyframe_points, points):
            key.co = (frame, value)
            key.interpolation = "LINEAR"
        fc.update()
    log_info(f"Reduced {len(proposals)} linear curves with channel error <= {factor}; original take retained.")


def transfer_animation(
    source_armature,
    target_armature,
    root_motion_mode=ROOT_SCALE,
    simplify_after_bake=False,
    simplify_factor=0.01,
    target_to_source_mapping=None,
):
    ok = transfer_animation_with_constraints(
        source_armature,
        target_armature,
        root_motion_mode=root_motion_mode,
        target_to_source_mapping=target_to_source_mapping,
    )
    if ok and simplify_after_bake:
        simplify_fcurves(target_armature, simplify_factor)
    if ok and target_armature.animation_data and target_armature.animation_data.action:
        action = target_armature.animation_data.action
        log_info(
            f"目标骨骼动画完成: {action.name}, F曲线={len(list(iter_action_fcurves(action, target_armature)))}, 帧范围={action.frame_range}"
        )
    return ok
