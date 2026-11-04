import math
import os
import re

import bpy

from .logger import log_info, log_warning


def read_bvh_framerate(bvh_path):
    try:
        with open(bvh_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "Frame Time:" in line:
                    match = re.search(r"Frame Time:\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", line)
                    if match:
                        frame_time = float(match.group(1))
                        if frame_time > 0:
                            fps = 1.0 / frame_time
                            log_info(f"检测到BVH帧率: {fps:.2f} FPS")
                            return fps
    except Exception as exc:
        log_warning(f"读取BVH帧率失败: {exc}")
    log_warning("未检测到BVH帧率，使用默认值: 30 FPS")
    return 30.0


def import_bvh(bvh_path, match_fps=True):
    bvh_path = os.path.abspath(os.path.expanduser(bpy.path.abspath(bvh_path)))
    if not os.path.exists(bvh_path) or not bvh_path.lower().endswith(".bvh"):
        return None, None

    bvh_fps = read_bvh_framerate(bvh_path)
    if match_fps:
        bpy.context.scene.render.fps = int(round(bvh_fps))
        bpy.context.scene.render.fps_base = 1.0
        log_info(f"场景帧率已设置为: {bpy.context.scene.render.fps} FPS")

    bpy.ops.import_anim.bvh(
        filepath=bvh_path,
        axis_forward="-Z",
        axis_up="Y",
        target="ARMATURE",
        use_fps_scale=not match_fps,
        update_scene_fps=match_fps,
        update_scene_duration=True,
        use_cyclic=False,
        rotate_mode="NATIVE",
    )

    armature = None
    for obj in bpy.context.selected_objects:
        if obj.type == "ARMATURE":
            armature = obj
            break
    if armature and armature.animation_data and armature.animation_data.action:
        start, end = armature.animation_data.action.frame_range
        bpy.context.scene.frame_start = math.floor(start)
        bpy.context.scene.frame_end = max(math.floor(start), math.ceil(end))
    return armature, bvh_fps
