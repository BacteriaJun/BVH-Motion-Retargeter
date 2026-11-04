"""Native cleanup/export-preflight regression tests; generated motion only.

Run Blender --background --factory-startup --disable-autoexec --python FILE
-- --output NEW_DIRECTORY. JSON separates mathematical/representation checks
from real-capture quality; no customer assets are loaded or bundled.
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
from bvh_to_mixamo.core.animation_utils import action_fcurve_collection, iter_action_fcurves
from bvh_to_mixamo.core.armature_utils import process_bones
from bvh_to_mixamo.core.bone_mapping import get_default_mapping
from bvh_to_mixamo.core.bvh_parser import import_bvh
from bvh_to_mixamo.core.export_profiles import export_preflight
from bvh_to_mixamo.core.motion_cleanup import audit_motion, cleanup_rotations, repair_root_gap
from bvh_to_mixamo.core.motion_math import distance_degrees

spec = importlib.util.spec_from_file_location("generated_cleanup_fixture", ROOT / "tests/make_motion_fixture.py")
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def curves(action, owner):
    return sorted(
        (
            c.data_path,
            c.array_index,
            c.extrapolation,
            c.mute,
            tuple(
                (
                    tuple(k.co),
                    tuple(k.handle_left),
                    tuple(k.handle_right),
                    k.interpolation,
                    k.handle_left_type,
                    k.handle_right_type,
                )
                for k in c.keyframe_points
            ),
        )
        for c in iter_action_fcurves(action, owner)
    )


def bone_channels(bone):
    return (
        bone.rotation_mode,
        tuple(bone.location),
        tuple(bone.rotation_euler),
        tuple(bone.rotation_quaternion),
        tuple(bone.rotation_axis_angle),
        tuple(bone.scale),
    )


def create_rig(directory, name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = directory / (name + ".bvh")
    fixture_module.write_fixture(path)
    rig, fps = import_bvh(str(path), True)
    assert rig is not None and abs(fps - 30) < 1e-6
    process_bones(rig, get_default_mapping())
    assert rig.animation_data.action is not None
    return rig, path


def sample(rig, names, frames):
    old, sub = bpy.context.scene.frame_current, bpy.context.scene.frame_subframe
    values = []
    try:
        for frame in frames:
            integer = math.floor(frame)
            bpy.context.scene.frame_set(integer, subframe=frame - integer)
            values.append({n: bone_channels(rig.pose.bones[n]) for n in names})
    finally:
        bpy.context.scene.frame_set(old, subframe=sub)
    return values


def replace_curve(rig, bone_name, channel, index, values, interpolation="LINEAR"):
    action = rig.animation_data.action
    collection = action_fcurve_collection(action, rig)
    path = rig.pose.bones[bone_name].path_from_id(channel)
    for c in list(collection):
        if c.data_path == path and c.array_index == index:
            collection.remove(c)
    fc = collection.new(
        path, index=index, **({"action_group": bone_name} if hasattr(action, "fcurves") else {"group_name": bone_name})
    )
    fc.keyframe_points.add(len(values))
    for key, (frame, value) in zip(fc.keyframe_points, values):
        key.co = frame, value
        key.interpolation = interpolation
    fc.update()
    return fc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    results = []

    def run(name, function):
        try:
            detail = function() or {}
            results.append({"id": name, "passed": True, "detail": detail})
        except Exception as error:
            results.append({"id": name, "passed": False, "error": str(error), "traceback": traceback.format_exc()})
        print(name, results[-1]["passed"], results[-1].get("error", ""), flush=True)

    def test_source_and_protected_channels():
        rig, path = create_rig(directory, "cleanup_scope")
        source_action = rig.animation_data.action
        before_curves = curves(source_action, rig)
        source_sha = digest(path)
        bpy.context.scene.frame_set(17, subframe=0.375)
        before_pose = {b.name: bone_channels(b) for b in rig.pose.bones}
        protected = [b.name for b in rig.pose.bones if "Index" in b.name]
        old = sample(rig, protected + ["mixamorig:Hips"], range(1, 62))
        root_path = rig.pose.bones["mixamorig:Hips"].path_from_id("location")
        protected_curve_keys = [c for c in before_curves if "Index" in c[0] or c[0] == root_path]
        out, report = cleanup_rotations(bpy.context, rig, strength=1, cap_degrees=3)
        assert out is not rig and out.data is not rig.data
        assert out.animation_data.action is not source_action
        assert rig.animation_data.action is source_action
        assert before_curves == curves(source_action, rig), "Original Action changed."
        assert {b.name: bone_channels(b) for b in rig.pose.bones} == before_pose, "Original pose values changed."
        assert bpy.context.scene.frame_current == 17 and abs(bpy.context.scene.frame_subframe - 0.375) < 1e-8
        assert digest(path) == source_sha
        now = sample(out, protected + ["mixamorig:Hips"], range(1, 62))
        for old_frame, new_frame in zip(old, now):
            for name in protected:
                assert old_frame[name] == new_frame[name], "Finger local channel changed."
            assert old_frame["mixamorig:Hips"][1] == new_frame["mixamorig:Hips"][1], "Root location changed."
        out_keys = [c for c in curves(out.animation_data.action, out) if "Index" in c[0] or c[0] == root_path]
        assert protected_curve_keys == out_keys, "Protected key/handle/interpolation changed."
        return {
            "protected_finger_bones": protected,
            "all_61_source_samples_preserved": True,
            "source_pose_and_frame_subframe_restored": True,
            "source_file_sha256": source_sha,
            "maximum_reported_correction_degrees": report["max_correction_degrees"],
            "action_model": "legacy" if hasattr(source_action, "fcurves") else "layered",
        }

    def test_noise_truth_and_cap():
        rig, path = create_rig(directory, "truth_noise")
        # Produce a clean source independently from the generated noisy motion.
        text = path.read_text(encoding="utf-8")
        hierarchy, motion = text.split("MOTION", 1)
        order = [line.split()[1] for line in hierarchy.splitlines() if line.strip().startswith(("ROOT ", "JOINT "))]
        rows = motion.strip().splitlines()
        column = 3 + 3 * order.index("LeftArm")
        for i in range(61):
            values = rows[i + 2].split()
            values[column] = str(float(values[column]) - 3 * (-1) ** i)
            rows[i + 2] = " ".join(values)
        truth_path = directory / "known_truth.bvh"
        truth_path.write_text(hierarchy + "MOTION\n" + "\n".join(rows) + "\n", encoding="utf-8")
        truth_rig, _ = import_bvh(str(truth_path), True)
        process_bones(truth_rig, get_default_mapping())
        out, report = cleanup_rotations(bpy.context, rig, strength=1, cap_degrees=3)
        errors = {"raw": [], "filtered": []}
        maximum = 0.0
        for frame in range(1, 62):
            bpy.context.scene.frame_set(frame)
            q = tuple(rig.pose.bones["mixamorig:LeftArm"].matrix_basis.to_quaternion())
            qout = tuple(out.pose.bones["mixamorig:LeftArm"].matrix_basis.to_quaternion())
            truth = tuple(truth_rig.pose.bones["mixamorig:LeftArm"].matrix_basis.to_quaternion())
            maximum = max(maximum, distance_degrees(q, qout))
            if 5 <= frame <= 57:
                errors["raw"].append(distance_degrees(q, truth))
                errors["filtered"].append(distance_degrees(qout, truth))
        rmse = {k: math.sqrt(sum(x * x for x in v) / len(v)) for k, v in errors.items()}
        assert maximum <= 3.0001, maximum
        assert rmse["filtered"] < rmse["raw"] * 0.75, rmse
        return {
            "known_truth_rotation_RMSE_degrees": rmse,
            "maximum_correction_degrees": maximum,
            "known_truth_is_synthetic": True,
            "industrial_capture_quality_claim": False,
        }

    def test_euler_full_turn_compatibility():
        rig, _ = create_rig(directory, "euler_turn")
        name = "mixamorig:LeftArm"
        rig.pose.bones[name].rotation_mode = "XYZ"
        values = [(i + 1, math.radians(355 + i / 6 + 2.5 * (-1) ** i)) for i in range(61)]
        for axis in range(3):
            replace_curve(rig, name, "rotation_euler", axis, [(f, v if axis == 2 else 0.0) for f, v in values])
        out, report = cleanup_rotations(bpy.context, rig, strength=1, cap_degrees=3, bone_names=[name])
        max_delta = 0.0
        for frame in range(1, 62):
            bpy.context.scene.frame_set(frame)
            p, q = rig.pose.bones[name], out.pose.bones[name]
            assert q.rotation_euler.z > math.radians(300), tuple(q.rotation_euler)
            max_delta = max(
                max_delta,
                distance_degrees(tuple(p.matrix_basis.to_quaternion()), tuple(q.matrix_basis.to_quaternion())),
            )
        assert max_delta <= 3.0001
        return {"authored_355_to_365_degree_neighborhood_preserved": True, "max_correction_degrees": max_delta}

    def test_zero_strength_preserves_bezier():
        rig, _ = create_rig(directory, "zero_strength")
        name = "mixamorig:LeftArm"
        for axis in range(3):
            replace_curve(
                rig,
                name,
                "rotation_euler",
                axis,
                [(1.0, 0.0), (15.0, 0.15 if axis == 2 else 0.0), (45.0, -0.1 if axis == 2 else 0.0), (61.0, 0.0)],
                interpolation="BEZIER",
            )
        original = curves(rig.animation_data.action, rig)
        out, report = cleanup_rotations(bpy.context, rig, strength=0)
        assert curves(out.animation_data.action, out) == original, "Strength=0 changed sparse Bezier key metadata."
        assert report["max_correction_degrees"] < 1e-6
        for frame in [1.5, 5.25, 14.25, 29.75, 40.5, 50.25]:
            a = sample(rig, [name], [frame])[0][name]
            b = sample(out, [name], [frame])[0][name]
            assert a == b, "Strength=0 changed subframe evaluation."
        return {"all_curve_metadata_and_subframes_exactly_preserved": True}

    def test_gap_scope_and_refusal():
        rig, path = create_rig(directory, "root_gap")
        name = "mixamorig:Hips"
        truth = [(0.01 * i, 0.2 + 0.0001 * i * i, 0.0) for i in range(61)]
        bad = [
            tuple(v + (0.2 if 20 <= i <= 22 and axis == 1 else 0.0) for axis, v in enumerate(row))
            for i, row in enumerate(truth)
        ]
        for axis in range(3):
            replace_curve(rig, name, "location", axis, [(i + 1, p[axis]) for i, p in enumerate(bad)])
        original_action = rig.animation_data.action
        original_keys = curves(original_action, rig)
        objects = len(bpy.data.objects)
        for a, z, confirmation in [(21, 23, False), (59, 61, True), (21, 26, True)]:
            try:
                repair_root_gap(bpy.context, rig, a, z, confirmed=confirmation)
            except ValueError:
                pass
            else:
                raise AssertionError("Unconfirmed/terminal/long gap was accepted.")
            assert len(bpy.data.objects) == objects
            assert curves(original_action, rig) == original_keys
        out, report = repair_root_gap(bpy.context, rig, 21, 23, confirmed=True)
        assert curves(original_action, rig) == original_keys
        max_truth_error = 0.0
        for i, frame in enumerate(range(1, 62)):
            bpy.context.scene.frame_set(frame)
            actual = tuple(out.pose.bones[name].location)
            if 20 <= i <= 22:
                max_truth_error = max(max_truth_error, math.dist(actual, truth[i]))
                assert math.dist(actual, truth[i]) < 2e-6
            else:
                assert actual == tuple(rig.pose.bones[name].location), "Non-gap root sample changed."
            for p in rig.pose.bones:
                assert tuple(out.pose.bones[p.name].rotation_euler) == tuple(p.rotation_euler)
        for c in curves(out.animation_data.action, out):
            if c[0] != out.pose.bones[name].path_from_id("location"):
                assert c in original_keys, "Unrelated curve changed."
        return {
            "only_root_frames_21_through_23_changed": True,
            "max_known_truth_error_units": max_truth_error,
            "gap_report": report,
            "rejected_unconfirmed_terminal_and_overlong": True,
        }

    def test_severe_tail_preflight_and_trim():
        rig, _ = create_rig(directory, "bad_tail")
        root = "mixamorig:Hips"
        location = [(i + 1, 348.0 if i >= 58 else 0.001 * i) for i in range(61)]
        replace_curve(rig, root, "location", 0, location)
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 61
        audit = audit_motion(bpy.context, rig)
        assert audit["max_root_step_L"] > 300, audit
        try:
            export_preflight(bpy.context, rig)
        except ValueError:
            pass
        else:
            raise AssertionError("Severe terminal source error exported without explicit allowance.")
        bpy.context.scene.frame_end = 58
        valid = export_preflight(bpy.context, rig)
        assert not valid["severe_discontinuity_frames"]
        return {
            "full_tail_rejected": True,
            "trimmed_scene_range_accepted": True,
            "full_max_root_step_L": audit["max_root_step_L"],
            "trimmed_range": valid["frame_range"],
        }

    def test_object_motion_preflight():
        rig, _ = create_rig(directory, "object_bad_tail")
        for frame in range(1, 62):
            rig.location = (0.0, 0.0, 0.0) if frame < 59 else (350.0, 0.0, 0.0)
            rig.keyframe_insert("location", frame=frame)
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 61
        try:
            export_preflight(bpy.context, rig)
        except ValueError:
            return {"animated_armature_object_tail_rejected": True}
        raise AssertionError("Armature object motion bypassed root preflight.")

    def test_nonuniform_or_animated_scale_rejected():
        rig, _ = create_rig(directory, "object_scale")
        rig.scale = (1.0, 2.0, 1.0)
        try:
            export_preflight(bpy.context, rig)
        except ValueError:
            pass
        else:
            raise AssertionError("Nonuniform object scale accepted by scale-aware preflight.")
        rig.scale = (1.0, 1.0, 1.0)
        for frame, value in [(1, 1.0), (61, 2.0)]:
            rig.scale = (value, value, value)
            rig.keyframe_insert("scale", frame=frame)
        try:
            export_preflight(bpy.context, rig)
        except ValueError:
            return {"nonuniform_and_animated_object_scale_rejected": True}
        raise AssertionError("Animated object scale accepted by scale-aware preflight.")

    def test_nonfinite_nonroot_channels_rejected():
        rig, _ = create_rig(directory, "nonfinite_hand_keys")
        replace_curve(rig, "mixamorig:LeftHand", "rotation_euler", 0, [(1.0, float("nan")), (61.0, float("nan"))])
        try:
            export_preflight(bpy.context, rig, allow_discontinuities=True)
        except ValueError:
            pass
        else:
            raise AssertionError("A nonroot NaN animation channel bypassed export preflight.")
        rig, _ = create_rig(directory, "nonfinite_hand_scale")
        rig.pose.bones["mixamorig:LeftHand"].scale = (float("nan"), 1.0, 1.0)
        try:
            export_preflight(bpy.context, rig, allow_discontinuities=True)
        except ValueError:
            return {
                "nonroot_key_and_evaluated_pose_finiteness_checked": True,
                "discontinuity_override_cannot_authorize_nonfinite_data": True,
            }
        raise AssertionError("A nonroot NaN evaluated pose bypassed export preflight.")

    for name, function in [
        ("original_action_pose_file_and_protected_channels", test_source_and_protected_channels),
        ("synthetic_noise_truth_improvement_and_3_degree_cap", test_noise_truth_and_cap),
        ("Euler_360_degree_neighborhood_compatibility", test_euler_full_turn_compatibility),
        ("zero_strength_keeps_sparse_Bezier_action_exact", test_zero_strength_preserves_bezier),
        ("confirmed_short_root_gap_scope_and_rejections", test_gap_scope_and_refusal),
        ("severe_root_tail_preflight_and_trim", test_severe_tail_preflight_and_trim),
        ("animated_armature_object_motion_cannot_bypass_preflight", test_object_motion_preflight),
        ("nonuniform_animated_scale_abstains", test_nonuniform_or_animated_scale_rejected),
        ("nonfinite_nonroot_data_cannot_export", test_nonfinite_nonroot_channels_rejected),
    ]:
        run(name, function)
    report = {
        "blender_version": bpy.app.version_string,
        "checks": results,
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "scope": "Native generated-fixture cleanup, preservation and export preflight. Not user-capture motion quality.",
        "source_hashes": {
            name: digest(ROOT / "bvh_to_mixamo/core" / name)
            for name in ["motion_math.py", "motion_cleanup.py", "animation_utils.py", "export_profiles.py"]
        },
    }
    (directory / "cleanup_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["passed"] == report["total"], [(r["id"], r.get("error")) for r in results if not r["passed"]]


if __name__ == "__main__":
    main()
