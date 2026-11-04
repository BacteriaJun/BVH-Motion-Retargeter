"""Actual registered-operator integration, using only generated fixtures.

blender --background --factory-startup --disable-autoexec --python-exit-code 1
        --python FILE -- --output NEW_DIR
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bvh_to_mixamo as addon
from bvh_to_mixamo.core import vmd_codec as codec
from bvh_to_mixamo.core.animation_utils import iter_action_fcurves
from bvh_to_mixamo.core.vmd_blender import create_preview_armature
from bvh_to_mixamo.ui.panel import MIXAMO_PT_panel


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture():
    bones = []
    for frame in range(31):
        # A known 100ms capture packet error; used only in an explicit confirmed
        # root-repair test, never inferred from a labelled real video.
        x = 0.01 * frame + (2.2 if 14 <= frame <= 16 else 0.0)
        bones.append(codec.BoneFrame("センター", frame, (x, 0.0, 0.0)))
        angle = math.radians(2.5) * math.sin(2 * math.pi * 8 * frame / 30)
        bones.append(codec.BoneFrame("頭", frame, rotation=(0.0, 0.0, math.sin(angle / 2), math.cos(angle / 2))))
    bones += [
        codec.BoneFrame("左人指1", 0),
        codec.BoneFrame("左人指1", 30, (0.1, 0.0, 0.1), (0.0, math.sin(0.15), 0.0, math.cos(0.15))),
        codec.BoneFrame("未対応骨", 9, (0.2, 0.3, 0.4)),
    ]
    return codec.Motion(
        model_name="Operator test",
        bones=bones,
        morphs=[codec.MorphFrame("笑い", 11, 0.2)],
        cameras=[codec.CameraFrame(2, distance=-25.0)],
        lights=[codec.LightFrame(3)],
        shadows=[codec.ShadowFrame(7, mode=1, distance=0.2)],
        ik_frames=[codec.IKFrame(0, True, [codec.IKState("左足ＩＫ", False)])],
        opaque_tail=b"operator_fixture_tail",
    )


def extras(motion):
    result = copy.deepcopy(motion)
    result.bones = []
    return codec.dumps(result)


def select(obj):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for old in bpy.context.selected_objects:
        old.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def invoke(op, expected="FINISHED"):
    try:
        result = op()
    except RuntimeError:
        if expected == "CANCELLED":
            return {"CANCELLED"}
        raise
    assert expected in result, (op, result, expected)
    return result


def action_values(rig, *, location=False, finger=False):
    data = []
    for curve in iter_action_fcurves(rig.animation_data.action, rig):
        if location and not curve.data_path.endswith(".location"):
            continue
        if finger and "左人指1" not in curve.data_path:
            continue
        data.append(
            [
                curve.data_path,
                curve.array_index,
                [[float(k.co.x), float(k.co.y), k.interpolation] for k in curve.keyframe_points],
            ]
        )
    return sorted(data, key=lambda row: (row[0], row[1]))


def scene_snapshot():
    scene = bpy.context.scene
    return {
        "objects": set(bpy.data.objects.keys()),
        "armatures": set(bpy.data.armatures.keys()),
        "actions": set(bpy.data.actions.keys()),
        "texts": set(bpy.data.texts.keys()),
        "fps": (scene.render.fps, scene.render.fps_base),
        "range": (scene.frame_start, scene.frame_end),
        "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        "selection": set(x.name for x in bpy.context.selected_objects),
        "last_output": scene.bvh_last_output_armature,
    }


def write_bvh(path):
    """Small independent complete humanoid with no customer poses or geometry."""
    rows = [
        ("Hips", None, (0.0, 0.0, 0.0)),
        ("Spine", "Hips", (0.0, 0.2, 0.0)),
        ("Spine1", "Spine", (0.0, 0.15, 0.0)),
        ("Spine2", "Spine1", (0.0, 0.15, 0.0)),
        ("Neck", "Spine2", (0.0, 0.13, 0.0)),
        ("Head", "Neck", (0.0, 0.1, 0.0)),
    ]
    for side, sign in [("Left", 1), ("Right", -1)]:
        for suffix, parent, offset in [
            ("Shoulder", "Spine2", (0.1, 0.1, 0.0)),
            ("Arm", side + "Shoulder", (0.1, 0.0, 0.0)),
            ("ForeArm", side + "Arm", (0.3, 0.0, 0.0)),
            ("Hand", side + "ForeArm", (0.25, 0.0, 0.0)),
            ("UpLeg", "Hips", (0.1, -0.05, 0.0)),
            ("Leg", side + "UpLeg", (0.0, -0.45, 0.0)),
            ("Foot", side + "Leg", (0.0, -0.45, 0.0)),
            ("ToeBase", side + "Foot", (0.0, 0.0, -0.12)),
        ]:
            rows.append((side + suffix, parent, (offset[0] * sign, offset[1], offset[2])))
        for finger, z in [("Thumb", -0.04), ("Index", -0.02), ("Middle", 0.0), ("Ring", 0.02), ("Pinky", 0.04)]:
            for number in range(1, 4):
                parent = side + "Hand" if number == 1 else side + "Hand" + finger + str(number - 1)
                rows.append(
                    (side + "Hand" + finger + str(number), parent, (0.035 * sign, 0.0, z if number == 1 else 0.0))
                )
    children = {name: [] for name, _, _ in rows}
    offsets = {name: offset for name, _, offset in rows}
    for name, parent, _ in rows:
        if parent is not None:
            children[parent].append(name)
    lines = ["HIERARCHY"]
    order = []

    def node(name, depth):
        indent = "  " * depth
        order.append(name)
        lines.extend(
            [
                indent + ("ROOT " if depth == 0 else "JOINT ") + name,
                indent + "{",
                indent + "  OFFSET " + " ".join(str(v) for v in offsets[name]),
                indent
                + "  CHANNELS "
                + (
                    "6 Xposition Yposition Zposition Zrotation Xrotation Yrotation"
                    if depth == 0
                    else "3 Zrotation Xrotation Yrotation"
                ),
            ]
        )
        for child in children[name]:
            node(child, depth + 1)
        if not children[name]:
            lines.extend([indent + "  End Site", indent + "  {", indent + "    OFFSET 0.03 0 0", indent + "  }"])
        lines.append(indent + "}")

    node("Hips", 0)
    lines += ["MOTION", "Frames: 31", "Frame Time: 0.0333333333333"]
    for frame in range(31):
        values = [0.001 * frame, 1.0, 0.0, 0.0, 0.0, 0.0]
        for name in order[1:]:
            angle = 2.0 * math.sin(2 * math.pi * 6 * frame / 30) if name == "Head" else 0.0
            values += [angle, 0.0, 0.0]
        lines.append(" ".join(f"{v:.9f}" for v in values))
    path.write_text("\n".join(lines) + "\n")


class UILayoutStub:
    def __init__(self):
        self.properties = []
        self.operators = []
        self.labels = []

    def row(self, **kwargs):
        return self

    def column(self, **kwargs):
        return self

    def box(self):
        return self

    def separator(self, **kwargs):
        pass

    def label(self, **kwargs):
        self.labels.append(kwargs.get("text", ""))

    def prop(self, owner, name, **kwargs):
        assert hasattr(owner, name), f"UI refers to missing property {name}"
        self.properties.append(name)

    def operator(self, name, **kwargs):
        category, operator = name.split(".")
        getattr(getattr(bpy.ops, category), operator).get_rna_type()
        self.operators.append(name)
        return SimpleNamespace()


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    checks = {}
    artifacts = {}
    previous_properties = {p for p in dir(bpy.types.Scene) if p.startswith("bvh_")}
    addon.register()
    introduced_properties = {p for p in dir(bpy.types.Scene) if p.startswith("bvh_")} - previous_properties
    assert len(introduced_properties) >= 30
    checks["addon_registration_properties_and_operators"] = True
    scene = bpy.context.scene
    for mode in ["VMD", "BVH"]:
        scene.bvh_source_format = mode
        stub = UILayoutStub()
        MIXAMO_PT_panel.draw(SimpleNamespace(layout=stub), bpy.context)
        assert stub.properties and stub.operators
        checks[f"{mode}_panel_draw_properties_and_registered_operator_ids"] = True
    source = output / "synthetic_source.vmd"
    motion = fixture()
    codec.write_vmd(source, motion, overwrite=True)
    source_bytes = source.read_bytes()
    motion = codec.loads(source_bytes)
    scene.bvh_source_format = "VMD"
    scene.bvh_vmd_input_path = str(source)
    scene.bvh_vmd_import_mode = "PREVIEW"
    invoke(bpy.ops.bvh.import_vmd)
    source_rig = bpy.context.view_layer.objects.active
    source_action = source_rig.animation_data.action
    assert source_rig["bvh_vmd_preview"]
    original_curves = action_values(source_rig)
    root_curves = action_values(source_rig, location=True)
    finger_curves = action_values(source_rig, finger=True)
    checks["registered_VMD_preview_import_created_editable_Action"] = True
    scene.bvh_cleanup_window = 0.12
    scene.bvh_cleanup_strength = 0.8
    scene.bvh_cleanup_cap = 3.0
    scene.bvh_cleanup_selected_bones = False
    invoke(bpy.ops.bvh.cleanup_motion)
    cleaned = bpy.context.view_layer.objects.active
    assert cleaned != source_rig and cleaned.animation_data.action != source_action
    assert action_values(source_rig) == original_curves
    assert action_values(cleaned, location=True) == root_curves
    assert action_values(cleaned, finger=True) == finger_curves
    assert float(cleaned["bvh_cleanup_max_angle_degrees"]) <= 3.0 + 1e-6
    assert cleaned["bvh_cleanup_max_angle_degrees"] > 0.0
    checks["registered_cleanup_copy_preserves_source_root_and_finger_keys"] = True
    cleaned_output = output / "cleaned_preserved.vmd"
    scene.bvh_vmd_output_path = str(cleaned_output)
    scene.bvh_vmd_export_mode = "PRESERVE"
    scene.bvh_export_overwrite = True
    invoke(bpy.ops.bvh.export_vmd)
    parsed = codec.read_vmd(cleaned_output)
    assert extras(parsed) == extras(motion)
    assert [f for f in parsed.bones if f.name == "左人指1"] == [f for f in motion.bones if f.name == "左人指1"]
    assert [f for f in parsed.bones if f.name == "未対応骨"] == [f for f in motion.bones if f.name == "未対応骨"]
    checks["registered_preserve_export_retains_extras_unknown_bones_and_fingers"] = True
    # The active original must win over the stale 'last output' pointing at copy.
    assert scene.bvh_last_output_armature == cleaned.name
    select(source_rig)
    active_output = output / "active_source_preserved.vmd"
    scene.bvh_vmd_output_path = str(active_output)
    invoke(bpy.ops.bvh.export_vmd)
    assert active_output.read_bytes() == source_bytes
    assert scene.bvh_last_output_armature == cleaned.name
    checks["active_source_wins_over_stale_last_output"] = True
    assert sha(source) == hashlib.sha256(source_bytes).hexdigest()
    checks["original_VMD_source_file_SHA_unchanged"] = True
    # Corrupt parse and a valid-but-enormous frame domain both leave no new rig,
    # Action, selection, FPS, or stale last-output pointer on cancellation.
    bad = output / "invalid.vmd"
    bad.write_bytes(b"not VMD")
    huge = output / "huge.vmd"
    codec.write_vmd(huge, codec.Motion(bones=[codec.BoneFrame("センター", 2_000_000)]), overwrite=True)
    for label, path in [("invalid_binary", bad), ("huge_sampling_domain", huge)]:
        scene.bvh_vmd_input_path = str(path)
        before = scene_snapshot()
        invoke(bpy.ops.bvh.import_vmd, "CANCELLED")
        assert scene_snapshot() == before, (label, scene_snapshot(), before)
        checks[label + "_preview_failure_rolls_back_all_data_and_context"] = True
    scene.bvh_vmd_input_path = str(source)
    # Root repair is a separate explicit operation, never part of denoising.
    scene.bvh_gap_start = 15
    scene.bvh_gap_end = 17
    scene.bvh_gap_root_bone = "センター"
    scene.bvh_gap_video_confirmed = False
    select(source_rig)
    before = scene_snapshot()
    invoke(bpy.ops.bvh.repair_root_gap, "CANCELLED")
    assert scene_snapshot() == before
    checks["unconfirmed_root_repair_does_not_create_copy"] = True
    scene.bvh_gap_video_confirmed = True
    invoke(bpy.ops.bvh.repair_root_gap)
    repaired = bpy.context.view_layer.objects.active
    assert repaired != source_rig
    assert action_values(source_rig) == original_curves
    repaired_output = output / "root_repair_preserved.vmd"
    scene.bvh_vmd_output_path = str(repaired_output)
    invoke(bpy.ops.bvh.export_vmd)
    assert extras(codec.read_vmd(repaired_output)) == extras(motion)
    checks["confirmed_short_root_repair_copy_preserves_original_and_extras"] = True
    # Real registered BVH conversion, followed by the new-FK VMD route.
    bvh = output / "synthetic_body.bvh"
    write_bvh(bvh)
    scene.bvh_source_format = "BVH"
    scene.bvh_input_path = str(bvh)
    scene.bvh_bind_mode = "CREATE"
    scene.bvh_target_skeleton = "MIXAMO"
    scene.bvh_auto_export_after_convert = False
    invoke(bpy.ops.mixamo.convert_bvh)
    converted = bpy.data.objects[scene.bvh_last_output_armature]
    select(converted)
    assert "mixamorig:Hips" in converted.data.bones
    scene.bvh_vmd_export_mode = "NEW_FK"
    scene.bvh_vmd_fk_mapping = "MIXAMO"
    scene.bvh_vmd_reference_scale = True
    new_vmd = output / "bvh_mixamo_new_fk.vmd"
    scene.bvh_vmd_output_path = str(new_vmd)
    invoke(bpy.ops.bvh.export_vmd)
    fk = codec.read_vmd(new_vmd)
    assert fk.bones and "センター" in {f.name for f in fk.bones}
    assert len(fk.ik_frames) == 1 and len(fk.ik_frames[0].states) == 4
    assert all(s.enabled is False for s in fk.ik_frames[0].states)
    checks["registered_BVH_Mixamo_new_FK_VMD_with_four_IK_disabled"] = True
    # Declared Japanese names must win over custom English Blender bone names.
    declared = create_preview_armature(bpy.context, name="Declared_name_test")
    declared.data.bones["センター"].name = "center_control"
    scene.bvh_source_format = "VMD"
    scene.bvh_vmd_import_mode = "SELECTED"
    scene.bvh_vmd_input_path = str(source)
    invoke(bpy.ops.bvh.import_vmd)
    scene.bvh_vmd_export_mode = "NEW_FK"
    scene.bvh_vmd_fk_mapping = "JAPANESE"
    scene.bvh_vmd_reference_scale = False
    # Source contains a synthetic reviewed root packet, explicitly permit that
    # discontinuity in this NEW-FK operator test, not as a production default.
    scene.bvh_export_allow_discontinuities = True
    declared_vmd = output / "declared_japanese_name.vmd"
    scene.bvh_vmd_output_path = str(declared_vmd)
    invoke(bpy.ops.bvh.export_vmd)
    names = {f.name for f in codec.read_vmd(declared_vmd).bones}
    assert "センター" in names and "center_control" not in names, names
    checks["new_FK_Japanese_mode_uses_declared_VMD_names"] = True
    artifacts = {
        "source": source.name,
        "cleaned": cleaned_output.name,
        "root_repair": repaired_output.name,
        "BVH_to_new_VMD": new_vmd.name,
        "declared_names": declared_vmd.name,
    }
    addon.unregister()
    assert not (introduced_properties & set(dir(bpy.types.Scene)))
    for cls in addon.classes:
        assert not cls.is_registered, cls.__name__
    checks["addon_unregister_removes_all_classes_and_Scene_properties"] = True
    # A second register/unregister cycle catches stale registration state.
    addon.register()
    addon.unregister()
    checks["addon_reregistration_cycle"] = True
    result = {
        "blender_version": bpy.app.version_string,
        "all_passed": all(checks.values()),
        "checks": checks,
        "artifacts": artifacts,
        "source_sha256": sha(source),
        "scope": "Actual registered bpy.ops plus schema-aware mocked panel drawing. Synthetic fixtures only; not MMD/UE native playback or customer-capture quality.",
    }
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    try:
        main(args.output)
    except Exception:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "failure.json").write_text(
            json.dumps({"error": traceback.format_exc(), "blender_version": bpy.app.version_string}, indent=2)
        )
        raise
