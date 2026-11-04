"""Run with Blender --background --factory-startup --disable-autoexec --python FILE -- --output DIR."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bvh_to_mixamo.core import vmd_codec as codec
from bvh_to_mixamo.core.animation_utils import iter_action_fcurves
from bvh_to_mixamo.core.vmd_blender import (
    SESSION_KEY,
    create_preview_armature,
    export_fk_motion,
    export_motion,
    import_motion,
    mmd_to_pose,
    pose_to_mmd,
)


def check_close(actual, expected, tolerance=2e-5):
    assert max(abs(a - b) for a, b in zip(actual, expected)) < tolerance, (actual, expected)


def fixture():
    q = (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))
    return codec.Motion(
        model_name="試験",
        bones=[
            codec.BoneFrame("センター", 0),
            codec.BoneFrame("センター", 30, (1.0, 2.0, 3.0), q),
            codec.BoneFrame("左人指1", 0),
            codec.BoneFrame("左人指1", 30, (0.1, 0.0, 0.3), q),
            codec.BoneFrame("未対応骨", 12, (0.5, 1.0, 2.0), q),
        ],
        morphs=[codec.MorphFrame("笑い", 7, 0.25)],
        cameras=[codec.CameraFrame(4, distance=-30.0, position=(1.0, 2.0, 3.0))],
        lights=[codec.LightFrame(2, color=(0.8, 0.7, 0.6))],
        shadows=[codec.ShadowFrame(3, mode=1, distance=0.25)],
        ik_frames=[codec.IKFrame(0, True, [codec.IKState("左足ＩＫ", False)])],
        opaque_tail=b"BVH_TEST_OPAQUE_VENDOR_TAIL",
    )


def extras_bytes(motion):
    import copy

    clone = copy.deepcopy(motion)
    clone.bones = []
    return codec.dumps(clone)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = p.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    directory = args.output
    checks = {}
    motion = fixture()
    source = directory / "source.vmd"
    codec.write_vmd(source, motion, overwrite=True)
    raw = source.read_bytes()
    motion = codec.loads(raw)
    rig = create_preview_armature(bpy.context, motion)
    assert len(rig.data.bones) >= 50
    assert rig["bvh_vmd_preview"]
    checks["canonical_reference_explicitly_labelled"] = True
    result = import_motion(bpy.context, source, rig)
    assert result["mapped_bones"] == 2
    assert result["unmapped_bone_names"] == ["未対応骨"]
    assert bpy.context.scene.render.fps == 30
    bpy.context.scene.frame_set(16)
    bone = rig.pose.bones["センター"]
    rest = bone.bone.matrix_local.to_3x3()
    world_delta = rest @ bone.location
    check_close(world_delta, (0.04, 0.12, 0.08))
    # Independent matrix conjugation expected from a +45deg MMD Z rotation.
    expected = Matrix.Rotation(-math.pi / 4, 3, "Y")
    observed = rest @ bone.rotation_quaternion.to_matrix() @ rest.inverted()
    check_close([x for row in observed for x in row], [x for row in expected for x in row])
    checks["MMD_basis_reflection_and_rest_axes_known_rotation"] = True
    finger = rig.pose.bones["左人指1"]
    assert abs(finger.bone.matrix_local.to_3x3()[0][0] - 1) > 0.01
    p0, q0 = (0.2, -0.7, 1.1), (0.1, 0.2, 0.3, math.sqrt(0.86))
    local, rotation = mmd_to_pose(finger.bone, p0, q0, 0.08)
    p1, q1 = pose_to_mmd(finger.bone, local, rotation, 0.08)
    check_close(p1, p0)
    assert abs(sum(a * b for a, b in zip(q0, q1))) > 1 - 1e-6
    checks["non_axis_aligned_finger_rest_basis_inverse"] = True
    untouched = directory / "untouched.vmd"
    report = export_motion(bpy.context, untouched, rig, overwrite=True)
    assert untouched.read_bytes() == raw
    assert report["untouched_file_byte_identical"]
    checks["untouched_import_export_byte_identical_all_sections"] = True
    # A local edit is made to exactly one pose-channel curve at one sampled key.
    action = rig.animation_data.action
    curve = next(
        c
        for c in iter_action_fcurves(action, rig)
        if c.data_path == finger.path_from_id("location") and c.array_index == 0
    )
    key = next(k for k in curve.keyframe_points if abs(k.co.x - 16.0) < 1e-6)
    key.co.y += 0.05
    curve.update()
    edited = directory / "edited.vmd"
    report = export_motion(bpy.context, edited, rig, overwrite=True)
    parsed = codec.read_vmd(edited)
    assert report["changed_bone_names"] == ["左人指1"]
    assert extras_bytes(parsed) == extras_bytes(motion)
    for name in ["センター", "未対応骨"]:
        assert [f for f in parsed.bones if f.name == name] == [f for f in motion.bones if f.name == name]
    assert len([f for f in parsed.bones if f.name == "左人指1"]) == 31
    assert (
        codec.sample_bone([f for f in parsed.bones if f.name == "左人指1"], 15)[0]
        != codec.sample_bone([f for f in motion.bones if f.name == "左人指1"], 15)[0]
    )
    checks["one_bone_edit_preserves_other_bones_extras_unknown_tail"] = True
    # The embedded source survives saving/reopening without sidecar disk paths.
    blend = directory / "editable_vmd.blend"
    rig_name = rig.name
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    rig = bpy.data.objects[rig_name]
    assert rig.animation_data.action.get(SESSION_KEY) in bpy.data.texts
    reopened = directory / "reopened_edited.vmd"
    export_motion(bpy.context, reopened, rig, overwrite=True)
    assert reopened.read_bytes() == edited.read_bytes()
    checks["blend_reopen_preserves_source_session_and_edited_export"] = True
    try:
        export_motion(bpy.context, source, rig)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Source overwrite was silently permitted")
    assert source.read_bytes() == raw
    checks["source_overwrite_refused_by_default"] = True
    # New-motion export uses a supplied name mapping and time-resamples 60 -> 30.
    bpy.context.scene.render.fps = 60
    new_file = directory / "new_fk_30fps.vmd"
    fk_report = export_fk_motion(
        bpy.context, new_file, rig, {"センター": "センター"}, frame_start=1, frame_end=61, overwrite=True
    )
    assert fk_report["sample_rate"] == 30 and fk_report["sampled_frames"] == 31
    assert max(f.frame for f in codec.read_vmd(new_file).bones) == 30
    fk_parsed = codec.read_vmd(new_file)
    assert len(fk_parsed.ik_frames) == 1 and fk_parsed.ik_frames[0].frame == 0
    assert [s.name for s in fk_parsed.ik_frames[0].states] == ["左足ＩＫ", "右足ＩＫ", "左つま先ＩＫ", "右つま先ＩＫ"]
    assert all(s.enabled is False for s in fk_parsed.ik_frames[0].states)
    checks["new_FK_motion_explicitly_disables_standard_leg_and_toe_IK"] = True
    checks["new_FK_export_explicit_mapping_60_to_30fps"] = True
    # Scale and FPS ambiguities cause refusal rather than silently changing units.
    try:
        export_motion(bpy.context, directory / "bad_fps.vmd", rig)
    except ValueError as exc:
        assert "FPS" in str(exc)
    else:
        raise AssertionError("Changed scene FPS accepted without time mapping")
    bpy.context.scene.render.fps = 30
    checks["ambiguous_FPS_change_refused"] = True
    # A 24fps timeline is sampled at real 1/30-second times rather than
    # silently treating Blender key indices as VMD frame numbers.
    bpy.context.scene.render.fps = 24
    file24 = directory / "new_fk_from_24fps.vmd"
    report24 = export_fk_motion(
        bpy.context, file24, rig, {"センター": "センター"}, frame_start=1, frame_end=25, overwrite=True
    )
    assert report24["sampled_frames"] == 31
    parsed24 = codec.read_vmd(file24)
    f15 = next(f for f in parsed24.bones if f.frame == 15)
    # At VMD frame15 (.5s), Blender24fps frame13 is read, not frame16.
    bpy.context.scene.frame_set(13)
    p24, _ = pose_to_mmd(
        rig.data.bones["センター"],
        rig.pose.bones["センター"].location,
        rig.pose.bones["センター"].rotation_quaternion,
        0.08,
    )
    check_close(f15.position, p24)
    checks["new_FK_export_24fps_time_based_sampling"] = True
    bpy.context.scene.render.fps = 30
    # Moving/reparenting a rig changes its calibration, even if bone names match.
    before_transform = rig.matrix_world.copy()
    rig.location.x += 0.2
    bpy.context.view_layer.update()
    try:
        export_motion(bpy.context, directory / "wrong_transform.vmd", rig)
    except ValueError as exc:
        assert "transform" in str(exc)
    else:
        raise AssertionError("Changed object calibration accepted")
    rig.matrix_world = before_transform
    bpy.context.view_layer.update()
    checks["changed_rig_object_transform_refused"] = True
    # Valid uint32 frame IDs can still be far too large to bake densely.
    huge = directory / "huge_frame.vmd"
    codec.write_vmd(huge, codec.Motion(bones=[codec.BoneFrame("センター", 1_000_000_000)]), overwrite=True)
    empty_rig = create_preview_armature(bpy.context, name="Budget_test")
    actions_before = set(bpy.data.actions.keys())
    scene_state = (
        bpy.context.scene.render.fps,
        bpy.context.scene.render.fps_base,
        bpy.context.scene.frame_start,
        bpy.context.scene.frame_end,
    )
    try:
        import_motion(bpy.context, huge, empty_rig)
    except ValueError as exc:
        assert "budget" in str(exc)
    else:
        raise AssertionError("Huge mapped VMD frame domain accepted")
    assert set(bpy.data.actions.keys()) == actions_before
    assert empty_rig.animation_data is None
    assert scene_state == (
        bpy.context.scene.render.fps,
        bpy.context.scene.render.fps_base,
        bpy.context.scene.frame_start,
        bpy.context.scene.frame_end,
    )
    checks["huge_frame_budget_refused_before_scene_or_action_mutation"] = True
    # Inject a failure during actual curve creation to exercise rollback after
    # scene FPS/action assignment, rather than only validating preflight paths.
    import bvh_to_mixamo.core.vmd_blender as bridge

    original_writer = bridge._write_curves

    def fail_writer(*args, **kwargs):
        raise RuntimeError("injected curve failure")

    bridge._write_curves = fail_writer
    old_action = rig.animation_data.action
    old_fake = old_action.use_fake_user
    actions_before = set(bpy.data.actions.keys())
    bpy.context.scene.render.fps = 24
    scene_state = (24, bpy.context.scene.render.fps_base, bpy.context.scene.frame_start, bpy.context.scene.frame_end)
    try:
        import_motion(bpy.context, source, rig, replace_action=True)
    except RuntimeError as exc:
        assert str(exc) == "injected curve failure"
    else:
        raise AssertionError("Injected failure was not propagated")
    finally:
        bridge._write_curves = original_writer
    assert rig.animation_data.action == old_action and old_action.use_fake_user == old_fake
    assert set(bpy.data.actions.keys()) == actions_before
    assert scene_state == (
        bpy.context.scene.render.fps,
        bpy.context.scene.render.fps_base,
        bpy.context.scene.frame_start,
        bpy.context.scene.frame_end,
    )
    checks["failed_import_rolls_back_action_FPS_range_and_old_take"] = True
    # Preserve an independent 60fps scene on import: VMD frame30 lands at61.
    bpy.context.scene.render.fps = 60
    import_motion(bpy.context, source, empty_rig, match_fps=False)
    assert bpy.context.scene.frame_end == 61
    bpy.context.scene.frame_set(31)
    check_close(
        empty_rig.data.bones["センター"].matrix_local.to_3x3() @ empty_rig.pose.bones["センター"].location,
        (0.04, 0.12, 0.08),
    )
    checks["import_to_60fps_scene_preserves_seconds"] = True
    bpy.context.scene.render.fps = 30
    bpy.context.scene.frame_set(16)
    center = rig.pose.bones["センター"]
    driver = center.driver_add("location", 0)
    driver.driver.expression = "2"
    bpy.context.scene.frame_set(17)
    try:
        export_motion(bpy.context, directory / "driven.vmd", rig)
    except ValueError as exc:
        assert "driver" in str(exc)
    else:
        raise AssertionError("Driver edit was silently exported as unchanged source")
    center.driver_remove("location", 0)
    bpy.context.scene.frame_set(16)
    checks["transform_driver_not_misclassified_as_untouched_track"] = True
    old_mode = center.rotation_mode
    center.rotation_mode = "XYZ"
    center.rotation_euler = (0, 0, 0)
    euler_path = directory / "changed_rotation_mode.vmd"
    mode_report = export_motion(bpy.context, euler_path, rig, overwrite=True)
    assert "センター" in mode_report["changed_bone_names"]
    center.rotation_mode = old_mode
    checks["rotation_mode_change_invalidates_untouched_track_digest"] = True
    center["test_ik_toggle"] = 1.0
    center.keyframe_insert(data_path='["test_ik_toggle"]', frame=1)
    try:
        export_motion(bpy.context, directory / "unsupported_property.vmd", rig)
    except ValueError as exc:
        assert "custom properties" in str(exc)
    else:
        raise AssertionError("Unsupported custom-property animation was silently discarded")
    checks["unsupported_IK_custom_property_animation_refused"] = True
    # Real vendor VMDs use fullwidth finger numbers. Matching may normalize
    # identifiers only; retained source names and re-exported bytes stay intact.
    alias_source = directory / "fullwidth_finger.vmd"
    alias_motion = codec.Motion(
        bones=[
            codec.BoneFrame("左人指１", 0),
            codec.BoneFrame("左人指１", 30, rotation=(0.0, 0.0, math.sin(0.2), math.cos(0.2))),
        ]
    )
    codec.write_vmd(alias_source, alias_motion, overwrite=True)
    alias_rig = create_preview_armature(bpy.context, alias_motion, name="Width_alias_test")
    alias_report = import_motion(bpy.context, alias_source, alias_rig)
    assert alias_report["mapped_bones"] == 1
    assert alias_report["mapped_bone_bindings"] == {"左人指１": "左人指1"}
    assert not alias_report["unmapped_bone_names"]
    alias_output = directory / "fullwidth_finger_preserved.vmd"
    export_motion(bpy.context, alias_output, alias_rig, overwrite=True)
    assert alias_output.read_bytes() == alias_source.read_bytes()
    checks["fullwidth_finger_alias_is_editable_without_renaming_source"] = True
    collision_source = directory / "colliding_width_names.vmd"
    codec.write_vmd(
        collision_source,
        codec.Motion(bones=[codec.BoneFrame("左人指１", 0), codec.BoneFrame("左人指1", 0)]),
        overwrite=True,
    )
    collision_rig = create_preview_armature(bpy.context, name="Alias_collision_test")
    action_count = len(bpy.data.actions)
    try:
        import_motion(bpy.context, collision_source, collision_rig)
    except ValueError as exc:
        assert "Ambiguous Unicode" in str(exc)
    else:
        raise AssertionError("Two source aliases were allowed to drive one target")
    assert len(bpy.data.actions) == action_count and collision_rig.animation_data is None
    checks["colliding_source_aliases_refused_before_mutation"] = True
    # New FK export cannot silently drop unbaked object placement or IK.
    guarded = create_preview_armature(bpy.context, name="New_FK_guard")
    import_motion(bpy.context, source, guarded)
    guarded.location.x = 0.1
    guarded.keyframe_insert(data_path="location", frame=1)
    refused_object = directory / "unbaked_object.vmd"
    if refused_object.exists():
        refused_object.unlink()
    try:
        export_fk_motion(bpy.context, refused_object, guarded, {"センター": "センター"})
    except ValueError as exc:
        assert "object/parent" in str(exc)
    else:
        raise AssertionError("New FK export silently dropped animated object placement")
    assert not refused_object.exists()
    checks["new_FK_unbaked_object_motion_refused_before_file_creation"] = True
    constrained = create_preview_armature(bpy.context, name="New_FK_constraint_guard")
    import_motion(bpy.context, source, constrained)
    constrained.pose.bones["センター"].constraints.new("LIMIT_LOCATION")
    refused_constraint = directory / "unbaked_constraint.vmd"
    if refused_constraint.exists():
        refused_constraint.unlink()
    try:
        export_fk_motion(bpy.context, refused_constraint, constrained, {"センター": "センター"})
    except ValueError as exc:
        assert "constraints/IK" in str(exc)
    else:
        raise AssertionError("New FK export silently ignored a bone constraint")
    assert not refused_constraint.exists()
    checks["new_FK_unbaked_bone_constraints_refused_before_file_creation"] = True
    driven_fk = create_preview_armature(bpy.context, name="New_FK_pose_driver")
    import_motion(bpy.context, source, driven_fk)
    pose_driver = driven_fk.pose.bones["センター"].driver_add("location", 0)
    pose_driver.driver.expression = "0.125"
    driven_file = directory / "new_fk_pose_driver.vmd"
    export_fk_motion(bpy.context, driven_file, driven_fk, {"センター": "センター"}, overwrite=True)
    driver_frame = next(frame for frame in codec.read_vmd(driven_file).bones if frame.frame == 0)
    assert abs(driver_frame.position[0] - 1.5625) < 1e-5
    checks["new_FK_pose_transform_driver_channels_can_be_explicitly_sampled"] = True
    chunk_rig = create_preview_armature(bpy.context, name="Chunk_storage_test")
    import_motion(bpy.context, source, chunk_rig)
    session_text = bpy.data.texts[chunk_rig.animation_data.action[SESSION_KEY]]
    stored = json.loads(session_text.as_string())
    assert "source_bytes_base64_chunks" in stored and "source_bytes_base64" not in stored
    assert max(len(line.body) for line in session_text.lines) <= 8220
    assert len(session_text.lines) > 10
    checks["source_session_uses_bounded_multiline_base64_chunks"] = True
    # A .blend saved by the initial pre-chunk implementation remains readable.
    stored["source_bytes_base64"] = "".join(stored.pop("source_bytes_base64_chunks"))
    session_text.clear()
    session_text.write(json.dumps(stored, ensure_ascii=False))
    legacy_output = directory / "legacy_session_preserved.vmd"
    export_motion(bpy.context, legacy_output, chunk_rig, overwrite=True)
    assert legacy_output.read_bytes() == source.read_bytes()
    checks["legacy_single_string_session_remains_byte_exact_readable"] = True
    summary = {
        "blender_version": bpy.app.version_string,
        "checks": checks,
        "all_passed": all(checks.values()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "edited_sha256": hashlib.sha256(edited.read_bytes()).hexdigest(),
        "import_report": result,
        "export_report": report,
        "scope": "Synthetic independently specified bone geometry/poses and actual Blender channel I/O. No PMX/MMD native IK, vendor VMD or end-user model playback acceptance.",
    }
    (directory / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
