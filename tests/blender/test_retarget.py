"""Native Constraint Bake and bounded curve reduction release regressions.

Generated same-rest rigs test representation/rollback, not retarget quality on
unknown anatomy. No private customer capture is used in this test suite.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bvh_to_mixamo.core import retarget_engine as engine
from bvh_to_mixamo.core.animation_utils import action_fcurve_collection, iter_action_fcurves
from bvh_to_mixamo.core.armature_utils import process_bones
from bvh_to_mixamo.core.bone_mapping import get_default_mapping
from bvh_to_mixamo.core.bvh_parser import import_bvh

spec = importlib.util.spec_from_file_location("retarget_generated_fixture", ROOT / "tests/make_motion_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
MARKERS = [
    "mixamorig:Hips",
    "mixamorig:Head",
    "mixamorig:LeftHand",
    "mixamorig:RightHand",
    "mixamorig:LeftFoot",
    "mixamorig:RightFoot",
    "mixamorig:LeftHandIndex1",
]


def curve_state(action, owner):
    if action is None:
        return []
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
            tuple(m.type for m in c.modifiers),
        )
        for c in iter_action_fcurves(action, owner)
    )


def bone_selected(p):
    return p.select if hasattr(p, "select") else p.bone.select


def set_bone_selected(p, value):
    if hasattr(p, "select"):
        p.select = value
    else:
        p.bone.select = value


def pose_state(rig):
    return {
        p.name: (
            p.rotation_mode,
            tuple(p.location),
            tuple(p.rotation_euler),
            tuple(p.rotation_quaternion),
            tuple(p.rotation_axis_angle),
            tuple(p.scale),
            bone_selected(p),
        )
        for p in rig.pose.bones
    }


def sample(rig, frames):
    current, sub = bpy.context.scene.frame_current, bpy.context.scene.frame_subframe
    out = []
    try:
        for f in frames:
            bpy.context.scene.frame_set(int(f), subframe=f - int(f))
            out.append([tuple(rig.matrix_world @ rig.pose.bones[n].head) for n in MARKERS])
    finally:
        bpy.context.scene.frame_set(current, subframe=sub)
    return out


def make_pair(folder, label, old_action=True):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source_path = folder / (label + ".bvh")
    fixture.write_fixture(source_path)
    source, _ = import_bvh(str(source_path), True)
    process_bones(source, get_default_mapping())
    source.name = "SourceRig"
    target = source.copy()
    target.data = source.data.copy()
    target.animation_data_clear()
    target.name = "TargetRig"
    bpy.context.collection.objects.link(target)
    if old_action:
        target.animation_data_create()
        target.animation_data.action = source.animation_data.action.copy()
        target.animation_data.action.name = "PriorCustomerTake"
        target.animation_data.action.use_fake_user = False
    for i, p in enumerate(target.pose.bones):
        set_bone_selected(p, bool(i % 2))
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = source
    bpy.context.scene.frame_set(17, subframe=0.375)
    return source, target, source_path


def context_state(source, target):
    ad = target.animation_data
    return {
        "source_scale": tuple(source.scale),
        "source_location": tuple(source.location),
        "source_pose": pose_state(source),
        "target_pose": pose_state(target),
        "frame": bpy.context.scene.frame_current,
        "subframe": bpy.context.scene.frame_subframe,
        "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        "mode": bpy.context.object.mode if bpy.context.object else "OBJECT",
        "selected": sorted(o.name for o in bpy.context.selected_objects),
        "target_action": ad.action.name if ad and ad.action else None,
        "had_animation_data": ad is not None,
        "action_names": sorted(a.name for a in bpy.data.actions),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    checks = []

    def run(name, function):
        try:
            detail = function()
            checks.append({"id": name, "passed": True, "detail": detail})
        except Exception as error:
            checks.append({"id": name, "passed": False, "error": str(error), "traceback": traceback.format_exc()})
        print(name, checks[-1]["passed"], checks[-1].get("error", ""), flush=True)

    def same_rest_bake():
        source, target, path = make_pair(folder, "same_rest")
        expected = sample(source, list(range(1, 62)))
        old = target.animation_data.action
        old_state = curve_state(old, target)
        source_action = source.animation_data.action
        source_state = curve_state(source_action, source)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert engine.transfer_animation_with_constraints(source, target, engine.ROOT_KEEP)
        observed = sample(target, list(range(1, 62)))
        error = max(math.dist(a, b) for row_a, row_b in zip(expected, observed) for a, b in zip(row_a, row_b))
        assert error < 3e-5, error
        assert target.animation_data.action is not old
        assert old.name in bpy.data.actions and old.use_fake_user
        assert curve_state(old, target) == old_state
        assert curve_state(source_action, source) == source_state
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        assert not target.constraints and all(not p.constraints for p in target.pose.bones)
        assert bpy.context.scene.frame_current == 17 and abs(bpy.context.scene.frame_subframe - 0.375) < 1e-8
        return {
            "max_same_rest_world_marker_error_units": error,
            "markers": len(MARKERS),
            "frames": 61,
            "prior_take_and_source_action_preserved": True,
            "no_temporary_constraints": True,
        }

    def existing_rig_reject():
        results = {}
        for kind in ["constraint", "driver", "NLA"]:
            source, target, _ = make_pair(folder, "existing_" + kind)
            if kind == "constraint":
                target.pose.bones["mixamorig:LeftHand"].constraints.new("COPY_ROTATION")
                target.constraints.new("COPY_LOCATION")
            elif kind == "driver":
                target.driver_add("location", 0).driver.expression = "0"
            else:
                track = target.animation_data.nla_tracks.new()
                track.strips.new("ExistingClip", 1, target.animation_data.action)
            before = context_state(source, target)
            action = target.animation_data.action
            keys = curve_state(action, target)
            counts = (
                len(target.constraints),
                sum(len(p.constraints) for p in target.pose.bones),
                len(target.animation_data.drivers),
                len(target.animation_data.nla_tracks),
            )
            assert engine.transfer_animation_with_constraints(source, target, engine.ROOT_KEEP) is False
            assert context_state(source, target) == before
            assert target.animation_data.action is action and curve_state(action, target) == keys
            assert counts == (
                len(target.constraints),
                sum(len(p.constraints) for p in target.pose.bones),
                len(target.animation_data.drivers),
                len(target.animation_data.nla_tracks),
            )
            results[kind] = "rejected_without_mutation"
        return results

    def source_transform_context_restore():
        source, target, _ = make_pair(folder, "source_restore")
        source.scale = (1.25, 1.25, 1.25)
        source.location = (2.1, -0.7, 0.4)
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.mode_set(mode="POSE")
        before = context_state(source, target)
        assert engine.transfer_animation_with_constraints(source, target, engine.ROOT_KEEP)
        after = context_state(source, target)
        for key in [
            "source_scale",
            "source_location",
            "source_pose",
            "frame",
            "subframe",
            "active",
            "mode",
            "selected",
        ]:
            assert after[key] == before[key], (key, before[key], after[key])
        assert all(bone_selected(p) == before["target_pose"][p.name][-1] for p in target.pose.bones)
        return {"source_transform_pose_frame_subframe_mode_and_selection_restored": True}

    def failed_bake_rollback(has_old_action):
        source, target, _ = make_pair(folder, "failure_" + str(has_old_action), old_action=has_old_action)
        source.scale = (1.3, 1.3, 1.3)
        source.location = (1.1, -0.2, 0.3)
        # Unkeyed scale and inactive rotation representations must also survive.
        target.pose.bones["mixamorig:LeftForeArm"].scale = (0.8, 1.1, 0.9)
        target.pose.bones["mixamorig:LeftForeArm"].rotation_quaternion = (0.7, 0.1, 0.2, 0.3)
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.mode_set(mode="POSE")
        before = context_state(source, target)
        old = target.animation_data.action if target.animation_data else None
        old_keys = curve_state(old, target)
        old_fake = old.use_fake_user if old else None
        old_bpy = engine.bpy

        def fail_bake(**_kwargs):
            partial = bpy.data.actions.new("InjectedPartialBake")
            target.animation_data_create()
            target.animation_data.action = partial
            b = target.pose.bones["mixamorig:LeftForeArm"]
            b.location = (0.3, 0.2, 0.1)
            b.rotation_euler = (0.8, -0.4, 0.2)
            b.rotation_quaternion = (0.2, 0.3, 0.4, 0.5)
            b.scale = (1.7, 0.6, 1.3)
            b.keyframe_insert("location", frame=42)
            bpy.context.scene.frame_set(42)
            # Real failures may occur after some constraints have been cleared.
            if b.constraints:
                b.constraints.remove(b.constraints[0])
            raise RuntimeError("Injected NLA bake failure after partial mutation")

        engine.bpy = SimpleNamespace(
            context=bpy.context,
            data=bpy.data,
            ops=SimpleNamespace(object=bpy.ops.object, nla=SimpleNamespace(bake=fail_bake)),
        )
        try:
            assert engine.transfer_animation_with_constraints(source, target, engine.ROOT_KEEP) is False
        finally:
            engine.bpy = old_bpy
        after = context_state(source, target)
        assert not target.constraints and all(not p.constraints for p in target.pose.bones), (
            "Temporary constraints survived failed bake."
        )
        assert after == before, {k: [before[k], after[k]] for k in before if before[k] != after[k]}
        if old is not None:
            assert target.animation_data.action is old and old.use_fake_user == old_fake
            assert curve_state(old, target) == old_keys
        return {"had_prior_take": has_old_action, "partial_action_constraints_pose_context_rolled_back": True}

    def curve_reduction():
        source, _, _ = make_pair(folder, "curve_reduction")
        action = source.animation_data.action
        collection = action_fcurve_collection(action, source)
        bezier = next(c for c in collection if "LeftForeArm" in c.data_path and c.array_index == 0)
        for key in bezier.keyframe_points:
            key.interpolation = "BEZIER"
        modified = next(c for c in collection if "RightForeArm" in c.data_path and c.array_index == 0)
        modified.modifiers.new("CYCLES")
        before = curve_state(action, source)
        sample_frames = [1 + i * 0.25 for i in range(241)]
        values = {
            (c.data_path, c.array_index): [c.evaluate(f) for f in sample_frames]
            for c in iter_action_fcurves(action, source)
        }
        count_before = sum(len(c.keyframe_points) for c in collection)
        engine.simplify_fcurves(source, factor=0.001)
        reduced = source.animation_data.action
        assert reduced is not action and action.use_fake_user
        assert curve_state(action, source) == before
        count_after = sum(len(c.keyframe_points) for c in iter_action_fcurves(reduced, source))
        assert count_after < count_before
        error = 0.0
        for c in iter_action_fcurves(reduced, source):
            error = max(
                error, max(abs(c.evaluate(f) - v) for f, v in zip(sample_frames, values[(c.data_path, c.array_index)]))
            )
        assert error <= 0.001001, error
        protected_ids = {(bezier.data_path, bezier.array_index), (modified.data_path, modified.array_index)}
        protected = {c[:2]: c for c in before if c[:2] in protected_ids}
        after = {c[:2]: c for c in curve_state(reduced, source)}
        assert all(after[key] == value for key, value in protected.items())
        return {
            "linear_key_count_before": count_before,
            "linear_key_count_after": count_after,
            "max_dense_channel_error": error,
            "budget_channel_units": 0.001,
            "Bezier_and_modified_channels_unchanged": True,
            "original_take_retained": True,
        }

    for name, function in [
        ("same_rest_ConstraintBake_world_trajectory", same_rest_bake),
        ("existing_target_constraint_driver_NLA_rejected", existing_rig_reject),
        ("source_transform_and_context_restored", source_transform_context_restore),
        ("failed_bake_prior_take_complete_rollback", lambda: failed_bake_rollback(True)),
        ("failed_bake_empty_target_complete_rollback", lambda: failed_bake_rollback(False)),
        ("linear_RDP_bound_and_Bezier_modifier_preservation", curve_reduction),
    ]:
        run(name, function)
    report = {
        "blender_version": bpy.app.version_string,
        "passed": sum(c["passed"] for c in checks),
        "total": len(checks),
        "checks": checks,
        "scope": "Generated native Constraint Bake, rollback and channel simplification. Not arbitrary-rig retarget accuracy.",
        "retarget_engine_sha256": hashlib.sha256(
            (ROOT / "bvh_to_mixamo/core/retarget_engine.py").read_bytes()
        ).hexdigest(),
    }
    (folder / "verification.json").write_text(json.dumps(report, indent=2))
    assert report["passed"] == report["total"], [(c["id"], c.get("error")) for c in checks if not c["passed"]]


if __name__ == "__main__":
    main()
