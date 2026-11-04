"""Generated-fixture Mixamo/UE4/UE5 native FBX round trips and root allocation.

These checks run inside Blender. No Epic engine or customer capture is needed;
passing them is not a claim of native Manny/Quinn skeleton identity or UE import.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bvh_to_mixamo.core.animation_utils import iter_action_fcurves
from bvh_to_mixamo.core.armature_utils import process_bones
from bvh_to_mixamo.core.bone_mapping import get_default_mapping
from bvh_to_mixamo.core.bvh_parser import import_bvh
from bvh_to_mixamo.core.export_profiles import (
    EXPORT_PROFILE_MIXAMO,
    EXPORT_PROFILE_UE4,
    EXPORT_PROFILE_UE5,
    export_armature_by_profile,
)
from bvh_to_mixamo.core.ue5_profile import (
    UE5_ROOT_BONE,
    UE5_ROOT_PELVIS,
    _ensure_root_bone,
    _split_pelvis_motion_to_root,
    convert_mixamo_armature_to_ue4_basic,
    convert_mixamo_armature_to_ue5_basic,
)

spec = importlib.util.spec_from_file_location("fbx_generated_fixture", ROOT / "tests/make_motion_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
COMMON = [
    "mixamorig:Hips",
    "mixamorig:Head",
    "mixamorig:LeftHand",
    "mixamorig:RightHand",
    "mixamorig:LeftFoot",
    "mixamorig:RightFoot",
    "mixamorig:LeftHandIndex1",
]
UE_NAMES = ["pelvis", "head", "hand_l", "hand_r", "foot_l", "foot_r", "index_01_l"]


def sample_world(rig, names, frames):
    old, sub = bpy.context.scene.frame_current, bpy.context.scene.frame_subframe
    out = []
    try:
        for f in frames:
            bpy.context.scene.frame_set(int(f), subframe=float(f) - int(f))
            out.append([tuple(rig.matrix_world @ rig.pose.bones[n].head) for n in names])
    finally:
        bpy.context.scene.frame_set(old, subframe=sub)
    return out


def difference(a, b):
    return max(math.dist(x, y) for xrow, yrow in zip(a, b) for x, y in zip(xrow, yrow))


def curve_values(rig):
    return sorted(
        (c.data_path, c.array_index, tuple((tuple(k.co), k.interpolation) for k in c.keyframe_points))
        for c in iter_action_fcurves(rig.animation_data.action, rig)
    )


def create(directory, name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = directory / (name + ".bvh")
    fixture.write_fixture(source)
    rig, _ = import_bvh(str(source), True)
    process_bones(rig, get_default_mapping())
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 61
    return rig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    records = []

    def run(name, function):
        try:
            detail = function()
            records.append({"id": name, "passed": True, "detail": detail})
        except Exception as error:
            records.append({"id": name, "passed": False, "error": str(error), "traceback": traceback.format_exc()})
        print(name, records[-1]["passed"], records[-1].get("error", ""), flush=True)

    def roundtrip(profile):
        rig = create(directory, profile)
        expected_before = sample_world(rig, COMMON, range(1, 62))
        if profile == EXPORT_PROFILE_UE4:
            convert_mixamo_armature_to_ue4_basic(rig, UE5_ROOT_PELVIS, True)
        elif profile == EXPORT_PROFILE_UE5:
            convert_mixamo_armature_to_ue5_basic(rig, UE5_ROOT_PELVIS, True)
        names = COMMON if profile == EXPORT_PROFILE_MIXAMO else UE_NAMES
        expected = sample_world(rig, names, range(1, 62))
        assert difference(expected_before, expected) < 2e-6
        bones = set(rig.data.bones.keys())
        if profile != EXPORT_PROFILE_MIXAMO:
            assert rig.data.bones["root"].parent is None
            assert tuple(rig.data.bones["root"].head_local) == (0.0, 0.0, 0.0)
            assert rig.data.bones["pelvis"].parent.name == "root"
            assert {"ik_foot_root", "ik_foot_l", "ik_hand_r"}.issubset(bones)
        keys = curve_values(rig)
        bpy.context.scene.frame_set(17, subframe=0.375)
        source_action = rig.animation_data.action
        selected = set(o.name for o in bpy.context.selected_objects)
        old_active = bpy.context.view_layer.objects.active
        output = directory / (profile + ".fbx")
        export_armature_by_profile(rig, str(output), profile, include_mesh=False)
        assert output.is_file() and output.stat().st_size > 1000
        assert curve_values(rig) == keys
        assert rig.animation_data.action == source_action
        assert bpy.context.view_layer.objects.active == old_active
        assert set(o.name for o in bpy.context.selected_objects) == selected
        # Exporter frame/subframe preservation is checked rather than assumed.
        assert bpy.context.scene.frame_current == 17 and abs(bpy.context.scene.frame_subframe - 0.375) < 1e-8
        original_bytes = output.read_bytes()
        try:
            export_armature_by_profile(rig, str(output), profile, include_mesh=False)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing FBX was overwritten without explicit allowance.")
        assert output.read_bytes() == original_bytes
        assert not list(directory.glob(".bvh-export-*"))
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = 30
        bpy.ops.import_scene.fbx(filepath=str(output), use_anim=True, anim_offset=0.0, automatic_bone_orientation=False)
        imported = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
        assert names == [n for n in names if n in imported.pose.bones]
        assert set(imported.data.bones.keys()) == bones, (bones, set(imported.data.bones.keys()))
        action = imported.animation_data.action
        start, end = action.frame_range
        assert round(end - start) + 1 == 61, (start, end)
        actual = sample_world(imported, names, [start + i for i in range(61)])
        error = difference(expected, actual)
        assert error < 2e-5, error
        return {
            "profile": profile,
            "sampled_frames": 61,
            "body_markers": len(names),
            "max_world_marker_roundtrip_error_units": error,
            "bone_count": len(bones),
            "native_reimport_action_range": [start, end],
            "sha256": hashlib.sha256(original_bytes).hexdigest(),
            "existing_output_protected": True,
            "no_temporary_export_leftovers": True,
            "direct_UE_engine_import_executed": False,
        }

    def split(profile, transformed, animated_object=False):
        rig = create(directory, profile + "_split")
        if transformed:
            rig.rotation_euler = (0.2, 0.35, 0.5)
            rig.location = (1.5, -0.3, 0.7)
            rig.scale = (2.0, 2.0, 2.0)
        if animated_object:
            for frame in range(1, 62):
                rig.rotation_euler = (0.1 + frame * 0.001, 0.2, 0.3 + frame * 0.003)
                rig.location = (frame * 0.005, -0.3, 0.7 + 0.04 * math.sin(frame / 30 * math.pi))
                rig.keyframe_insert("rotation_euler", frame=frame)
                rig.keyframe_insert("location", frame=frame)
        expected = sample_world(rig, COMMON, range(1, 62))
        before_action = rig.animation_data.action
        if profile == EXPORT_PROFILE_UE4:
            convert_mixamo_armature_to_ue4_basic(rig, UE5_ROOT_BONE, True)
        else:
            convert_mixamo_armature_to_ue5_basic(rig, UE5_ROOT_BONE, True)
        assert rig.animation_data.action is not before_action, "Root allocation must commit a separate Action."
        actual = sample_world(rig, UE_NAMES, range(1, 62))
        error = difference(expected, actual)
        assert error < 3e-6, error
        root = [row[0] for row in sample_world(rig, ["root"], range(1, 62))]
        height_range = max(p[2] for p in root) - min(p[2] for p in root)
        assert height_range < 2e-6, height_range
        pelvis = [row[0] for row in actual]
        max_planar_error = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(root, pelvis))
        assert max_planar_error < 3e-6, max_planar_error
        assert max(p[2] for p in pelvis) - min(p[2] for p in pelvis) > 0.02
        # Explicit duplicate split refusal; no repeated displacement allocation.
        saved = curve_values(rig)
        source_action = rig.animation_data.action
        try:
            _split_pelvis_motion_to_root(rig, UE5_ROOT_BONE)
        except ValueError:
            pass
        else:
            raise AssertionError("Second root split was accepted.")
        assert curve_values(rig) == saved and rig.animation_data.action == source_action
        suffix = "animated" if animated_object else ("transformed" if transformed else "split")
        output = directory / (profile + "_root_" + suffix + ".fbx")
        export_armature_by_profile(rig, str(output), profile, include_mesh=False)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = 30
        bpy.ops.import_scene.fbx(filepath=str(output), use_anim=True, anim_offset=0.0, automatic_bone_orientation=False)
        imported = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
        start, end = imported.animation_data.action.frame_range
        assert round(end - start) + 1 == 61
        native = sample_world(imported, UE_NAMES, [start + i for i in range(61)])
        native_root = [row[0] for row in sample_world(imported, ["root"], [start + i for i in range(61)])]
        export_error = difference(actual, native)
        root_error = max(math.dist(a, b) for a, b in zip(root, native_root))
        assert export_error < 3e-5, export_error
        assert root_error < 3e-5, root_error
        return {
            "profile": profile,
            "object_nonidentity_rotation_and_uniform_scale": transformed,
            "animated_object_rotation_and_vertical_motion": animated_object,
            "world_body_trajectory_max_error_units": error,
            "world_root_height_range_units": height_range,
            "world_root_to_pelvis_XY_error_units": max_planar_error,
            "root_motion_FBX_roundtrip_body_error_units": export_error,
            "root_motion_FBX_roundtrip_root_error_units": root_error,
            "vertical_body_motion_preserved": True,
            "duplicate_split_refused": True,
        }

    def existing_root_keys_refuse():
        rig = create(directory, "existing_root")
        convert_mixamo_armature_to_ue5_basic(rig, UE5_ROOT_PELVIS, False)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        existing = rig.data.edit_bones["root"]
        existing.head = (0.1, 0.2, 0.3)
        existing.tail = (0.1, 0.2, 0.4)
        bpy.ops.object.mode_set(mode="OBJECT")
        saved_head = tuple(rig.data.bones["root"].head_local)
        saved_tail = tuple(rig.data.bones["root"].tail_local)
        _ensure_root_bone(rig)
        assert tuple(rig.data.bones["root"].head_local) == saved_head
        assert tuple(rig.data.bones["root"].tail_local) == saved_tail
        rig.pose.bones["root"].keyframe_insert("location", frame=1)
        saved = curve_values(rig)
        source = rig.animation_data.action
        try:
            _split_pelvis_motion_to_root(rig, UE5_ROOT_BONE)
        except ValueError:
            assert curve_values(rig) == saved and rig.animation_data.action == source
            return {
                "existing_root_animation_is_not_duplicated_or_removed": True,
                "existing_nonzero_root_rest_origin_unchanged": True,
            }
        raise AssertionError("Root with existing authored keys was accepted.")

    def wrong_profile_refuse():
        rig = create(directory, "wrong_profile")
        target = directory / "wrong_unreal.fbx"
        try:
            export_armature_by_profile(rig, str(target), EXPORT_PROFILE_UE5, include_mesh=False)
        except ValueError:
            assert not target.exists()
            assert not list(directory.glob(".bvh-export-*"))
            return {"Mixamo_source_cannot_masquerade_as_UE_profile": True}
        raise AssertionError("UE export accepted a Mixamo-named skeleton.")

    for name, function in [
        ("mixamo_FBX_native_roundtrip", lambda: roundtrip(EXPORT_PROFILE_MIXAMO)),
        ("UE4_FBX_native_roundtrip", lambda: roundtrip(EXPORT_PROFILE_UE4)),
        ("UE5_FBX_native_roundtrip", lambda: roundtrip(EXPORT_PROFILE_UE5)),
        ("UE5_root_split_preserves_world_vertical_and_body", lambda: split(EXPORT_PROFILE_UE5, False)),
        ("UE4_root_split_nonidentity_object_rest_axes", lambda: split(EXPORT_PROFILE_UE4, True)),
        ("animated_object_root_split_world_plane", lambda: split(EXPORT_PROFILE_UE5, True, True)),
        ("existing_root_keys_split_refused", existing_root_keys_refuse),
        ("incompatible_FBX_profile_refused", wrong_profile_refuse),
    ]:
        run(name, function)
    report = {
        "blender_version": bpy.app.version_string,
        "passed": sum(r["passed"] for r in records),
        "total": len(records),
        "checks": records,
        "scope": "Native FBX representation, generated motion and root-allocation tests. No Epic engine was run.",
        "source_hashes": {
            n: hashlib.sha256((ROOT / "bvh_to_mixamo/core" / n).read_bytes()).hexdigest()
            for n in ["export_profiles.py", "ue5_profile.py", "animation_utils.py"]
        },
    }
    (directory / "fbx_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["passed"] == report["total"], [(r["id"], r.get("error")) for r in records if not r["passed"]]


if __name__ == "__main__":
    main()
