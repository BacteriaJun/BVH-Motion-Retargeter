"""Independent release counterexamples; run in a factory-startup Blender process."""

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bvh_to_mixamo.core import vmd_blender as bridge
from bvh_to_mixamo.core import vmd_codec as codec


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output
    source = output / "source.vmd"
    motion = codec.Motion(
        model_name="反例試験",
        bones=[
            codec.BoneFrame("センター", 0),
            codec.BoneFrame("センター", 30, (1, 2, 3)),
            codec.BoneFrame("未対応骨", 17, (0.2, 0.1, 0.3)),
        ],
        morphs=[codec.MorphFrame("笑い", 5, 0.2)],
        ik_frames=[codec.IKFrame(0, True, [codec.IKState("左足ＩＫ", True)])],
        opaque_tail=b"OPAQUE_CUSTOMER_TEST_SECTION",
    )
    codec.write_vmd(source, motion, overwrite=True)
    original_hash = digest(source)
    checks = []

    def run(name, function):
        try:
            detail = function() or {}
            checks.append({"id": name, "passed": True, "detail": detail})
        except Exception as exc:
            checks.append({"id": name, "passed": False, "exception": str(exc), "traceback": traceback.format_exc()})
        assert digest(source) == original_hash

    def imported(name, *, fps=30, base=1.0, match=True, start=1):
        bpy.context.scene.render.fps = fps
        bpy.context.scene.render.fps_base = base
        rig = bridge.create_preview_armature(bpy.context, name=name)
        report = bridge.import_motion(bpy.context, source, rig, match_fps=match, frame_start=start)
        return rig, report

    def driver_change():
        rig, _ = imported("driver_case")
        pose = rig.pose.bones["センター"]
        driver = pose.driver_add("location", 0)
        driver.driver.type = "SCRIPTED"
        driver.driver.expression = "2.0"
        bpy.context.scene.frame_set(2)
        assert abs(pose.location.x - 2) < 1e-6
        destination = output / "driver_edited.vmd"
        try:
            report = bridge.export_motion(bpy.context, destination, rig)
        except ValueError as exc:
            return {"refused": str(exc), "unsupported_driver_not_lost": True}
        assert "センター" in report["changed_bone_names"], (
            "A transform driver changes the pose but exporter reports untouched and returns source bytes"
        )
        result = codec.read_vmd(destination)
        assert [f for f in result.bones if f.name == "センター"] != [f for f in motion.bones if f.name == "センター"]
        return {"changed": report["changed_bone_names"]}

    run("mapped_pose_driver_must_refuse_or_export_edit", driver_change)

    def rollback_fake_user():
        rig = bridge.create_preview_armature(bpy.context, name="rollback_case")
        rig.animation_data_create()
        old = bpy.data.actions.new("Previous_take_without_fake_user")
        rig.animation_data.action = old
        old.use_fake_user = False
        scene = bpy.context.scene
        scene.render.fps = 48
        scene.frame_start = 4
        scene.frame_end = 100
        scene.frame_set(12)
        state = (
            old.use_fake_user,
            scene.render.fps,
            scene.frame_start,
            scene.frame_end,
            scene.frame_current,
            len(bpy.data.actions),
            len(bpy.data.texts),
        )
        original = bridge._curve_digest

        def fault(*args, **kwargs):
            raise RuntimeError("Injected failure after Action assignment; no customer data")

        bridge._curve_digest = fault
        try:
            try:
                bridge.import_motion(bpy.context, source, rig, replace_action=True)
            except RuntimeError as exc:
                assert "Injected" in str(exc)
            else:
                raise AssertionError("Injected import failure did not occur")
        finally:
            bridge._curve_digest = original
        assert rig.animation_data.action is old
        after = (
            old.use_fake_user,
            scene.render.fps,
            scene.frame_start,
            scene.frame_end,
            scene.frame_current,
            len(bpy.data.actions),
            len(bpy.data.texts),
        )
        assert state == after, f"Failed import changed preexisting state: {state} -> {after}"
        return {"all_snapshot_fields_restored": True}

    run("failed_import_restores_old_action_and_fake_user", rollback_fake_user)

    def rational_time():
        rig, r = imported("fps_case", fps=24, base=1.001, match=False, start=10)
        fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
        frame = 10 + 0.5 * fps
        bridge._set_frame(bpy.context.scene, frame)
        bone = rig.pose.bones["センター"]
        delta = bone.bone.matrix_local.to_3x3() @ bone.location
        expected = (0.04, 0.12, 0.08)
        assert max(abs(a - b) for a, b in zip(delta, expected)) < 2e-6, (delta, expected)
        p = output / "rational_fps.vmd"
        report = bridge.export_motion(bpy.context, p, rig)
        assert p.read_bytes() == source.read_bytes()
        return {
            "scene_fps": fps,
            "VMD_15_at_scene_frame": frame,
            "source_30fps_time_preserved": True,
            "byte_exact": report["untouched_file_byte_identical"],
        }

    run("rational_scene_fps_30fps_vmd_time", rational_time)

    def mismatch_scale():
        rig, _ = imported("scale_case")
        p = output / "wrong_scale.vmd"
        try:
            bridge.export_motion(bpy.context, p, rig, unit_scale=0.16)
        except ValueError as exc:
            assert "scale" in str(exc)
        else:
            raise AssertionError("Unit scale changed without explicit new-motion semantics")
        assert not p.exists()
        return {"rejected_before_file_creation": True}

    run("roundtrip_unit_change_refused", mismatch_scale)

    def max_budget():
        rig = bridge.create_preview_armature(bpy.context, name="bounded_case")
        p = output / "absurd_frames.vmd"
        codec.write_vmd(p, codec.Motion(bones=[codec.BoneFrame("センター", 1_000_000)]), overwrite=True)
        actions, texts = len(bpy.data.actions), len(bpy.data.texts)
        try:
            bridge.import_motion(bpy.context, p, rig)
        except ValueError as exc:
            assert "budget" in str(exc)
        else:
            raise AssertionError("Unbounded materialization")
        assert len(bpy.data.actions) == actions and len(bpy.data.texts) == texts
        return {"bounded_before_allocating_actions": True}

    run("max_sample_budget_preflights", max_budget)

    def duplicate_names():
        rig = bridge.create_preview_armature(bpy.context, name="name_collision_case")
        rig.data.bones["左腕"]["vmd_name"] = "センター"
        try:
            bridge.import_motion(bpy.context, source, rig)
        except ValueError as exc:
            assert "duplicate" in str(exc).lower()
        else:
            raise AssertionError("Multiple Blender bones share one VMD track")
        assert rig.animation_data is None
        return {"duplicate_binding_refused": True}

    run("duplicate_mmd_name_refused", duplicate_names)

    def changed_rest():
        rig, _ = imported("rest_case")
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        rig.data.edit_bones["センター"].roll += 0.1
        bpy.ops.object.mode_set(mode="OBJECT")
        p = output / "changed_rest.vmd"
        try:
            bridge.export_motion(bpy.context, p, rig)
        except ValueError as exc:
            assert "rest" in str(exc).lower()
        else:
            raise AssertionError("Changed rest orientation accepted with old session")
        assert not p.exists()
        return {"rest_change_refused": True}

    run("rest_geometry_change_refused", changed_rest)

    def existing_output_transaction():
        rig, _ = imported("overwrite_case")
        p = output / "existing_customer_result.vmd"
        p.write_bytes(b"customer existing output")
        scene = bpy.context.scene
        scene.frame_set(15, subframe=0.25)
        state = (scene.frame_current, scene.frame_subframe)
        try:
            bridge.export_motion(bpy.context, p, rig)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing output overwritten")
        assert p.read_bytes() == b"customer existing output"
        assert (scene.frame_current, scene.frame_subframe) == state
        return {"destination_preserved": True, "scene_time_restored": True}

    run("existing_output_protected_and_context_restored", existing_output_transaction)

    summary = {
        "scope": "Release development counterexamples in real Blender; synthetic files, not vendor/client VMD or MMD playback acceptance. Failed checks are retained and must not be reclassified as passed.",
        "blender": bpy.app.version_string,
        "checks": checks,
        "passed": sum(c["passed"] for c in checks),
        "total": len(checks),
        "source_file_unchanged": digest(source) == original_hash,
        "source_sha256": original_hash,
        "codec_sha256": digest(ROOT / "bvh_to_mixamo/core/vmd_codec.py"),
        "bridge_sha256": digest(ROOT / "bvh_to_mixamo/core/vmd_blender.py"),
    }
    (output / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
