import re

import bpy

from .animation_utils import iter_action_fcurves
from .bone_data import MIXAMO_BONE_HIERARCHY
from .bone_mapping import get_default_mapping
from .logger import log_info, log_warning


def is_mixamo_armature(armature):
    if not armature or armature.type != "ARMATURE":
        return False
    key_bones = ["mixamorig:Hips", "mixamorig:Spine", "mixamorig:LeftArm", "mixamorig:RightArm"]
    found = sum(1 for name in key_bones if name in armature.data.bones)
    return found >= 3


def get_selected_mixamo_armature():
    for obj in bpy.context.selected_objects:
        if is_mixamo_armature(obj):
            return obj
    return None


def find_mixamo_armature_in_objects(objects):
    armatures = [obj for obj in objects if obj and obj.type == "ARMATURE"]
    for armature in armatures:
        if is_mixamo_armature(armature):
            return armature
    return armatures[0] if armatures else None


def ensure_object_mode():
    try:
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass


def update_animation_bone_paths(armature, bone_mapping):
    if not armature.animation_data or not armature.animation_data.action:
        return 0
    action = armature.animation_data.action
    updated = 0
    for fcurve in iter_action_fcurves(action, armature):
        if "pose.bones[" not in fcurve.data_path:
            continue
        match = re.search(r'pose\.bones\["([^"]+)"\]', fcurve.data_path)
        if not match:
            continue
        old_name = match.group(1)
        if old_name in bone_mapping:
            new_name = bone_mapping[old_name]
            fcurve.data_path = fcurve.data_path.replace(f'pose.bones["{old_name}"]', f'pose.bones["{new_name}"]')
            updated += 1
    return updated


def process_bones(armature, bone_mapping=None, update_animation=True):
    if bone_mapping is None:
        bone_mapping = get_default_mapping()
    bpy.context.view_layer.objects.active = armature
    ensure_object_mode()
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones

    bvh_bone_names = set(bone.name for bone in edit_bones)
    keep_bvh_names = set(bone_mapping.keys())
    bones_to_delete = [name for name in bvh_bone_names if name not in keep_bvh_names]
    for end_bone in ["HeadTop_End", "LeftToeEnd", "RightToeEnd"]:
        if end_bone in edit_bones and end_bone not in bones_to_delete:
            bones_to_delete.append(end_bone)
    for name in bones_to_delete:
        if name in edit_bones:
            edit_bones.remove(edit_bones[name])
    log_info(f"清理多余骨骼: 共删除 {len(bones_to_delete)} 个")

    bpy.ops.object.mode_set(mode="OBJECT")
    if update_animation:
        updated = update_animation_bone_paths(armature, bone_mapping)
        log_info(f"更新了 {updated} 条F曲线的骨骼引用")

    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones
    mapped = 0
    for old_name, new_name in bone_mapping.items():
        if old_name in edit_bones:
            edit_bones[old_name].name = new_name
            mapped += 1
    log_info(f"骨骼名称映射: 成功映射 {mapped} 个核心骨骼")

    for parent_name, child_names in MIXAMO_BONE_HIERARCHY.items():
        if parent_name not in edit_bones:
            continue
        parent = edit_bones[parent_name]
        for child_name in child_names:
            if child_name not in edit_bones:
                continue
            child = edit_bones[child_name]
            head = child.head.copy()
            tail = child.tail.copy()
            roll = child.roll
            child.parent = parent
            child.use_connect = False
            child.head = head
            child.tail = tail
            child.roll = roll
            if child.length < 0.001:
                child.tail = (
                    child.head + (tail - head).normalized() * 0.01 if (tail - head).length > 0 else child.head.copy()
                )

    if "mixamorig:Hips" in edit_bones:
        hips = edit_bones["mixamorig:Hips"]
        for leg_name in ("mixamorig:LeftUpLeg", "mixamorig:RightUpLeg"):
            if leg_name in edit_bones:
                edit_bones[leg_name].parent = hips
                edit_bones[leg_name].use_connect = False

    for bone in edit_bones:
        if bone.parent:
            bone.use_connect = False

    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    log_info("骨骼层级修复完成")
    return armature


def verify_animation_data(armature):
    if not armature.animation_data or not armature.animation_data.action:
        log_warning("骨架没有动画数据")
        return False
    action = armature.animation_data.action
    if len(list(iter_action_fcurves(action, armature))) == 0:
        log_warning("动画没有关键帧曲线")
        return False
    total_keyframes = sum(len(fc.keyframe_points) for fc in iter_action_fcurves(action, armature))
    log_info(
        f"动画数据验证: {action.name}, F曲线={len(list(iter_action_fcurves(action, armature)))}, 关键帧={total_keyframes}, 帧范围={action.frame_range}"
    )
    return True


def bone_world_rest_matrix(armature, bone_name):
    bone = armature.data.bones.get(bone_name)
    if not bone:
        return None
    return armature.matrix_world @ bone.matrix_local


def estimate_leg_length(armature):
    chains = [
        ("mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot"),
        ("mixamorig:RightUpLeg", "mixamorig:RightLeg", "mixamorig:RightFoot"),
    ]
    lengths = []
    for chain in chains:
        total = 0.0
        valid = True
        for bone_name in chain:
            bone = armature.data.bones.get(bone_name)
            if not bone:
                valid = False
                break
            total += bone.length
        if valid and total > 0:
            lengths.append(total)
    return sum(lengths) / len(lengths) if lengths else 0.0


def calculate_motion_scale(source_armature, target_armature):
    source_leg = estimate_leg_length(source_armature)
    target_leg = estimate_leg_length(target_armature)
    if source_leg > 0 and target_leg > 0:
        ratio = target_leg / source_leg
        log_info(f"Motion Scale按腿长计算: source={source_leg:.4f}, target={target_leg:.4f}, ratio={ratio:.4f}")
        return ratio
    source_hips = source_armature.data.bones.get("mixamorig:Hips")
    target_hips = target_armature.data.bones.get("mixamorig:Hips")
    if source_hips and target_hips and source_hips.length > 0:
        ratio = target_hips.length / source_hips.length
        log_warning(f"腿长不可用，回退到Hips比例: {ratio:.4f}")
        return ratio
    log_warning("无法计算比例，使用1.0")
    return 1.0
