"""Public bundled-character skinning and generated-motion native FBX pipeline.

This checks format/deformation preservation against the exported target, not
retarget accuracy across different rest poses or faithful capture recovery.
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
from bvh_to_mixamo.core.armature_utils import process_bones
from bvh_to_mixamo.core.bone_mapping import get_default_mapping
from bvh_to_mixamo.core.bvh_parser import import_bvh
from bvh_to_mixamo.core.export_profiles import EXPORT_PROFILE_MIXAMO, export_armature_by_profile
from bvh_to_mixamo.core.retarget_engine import ROOT_SCALE, transfer_animation_with_constraints
from bvh_to_mixamo.core.template_loader import import_character_template_fbx
from bvh_to_mixamo.core.ue5_profile import get_armature_meshes
from scripts.fetch_templates import TEMPLATE_SHA256

spec = importlib.util.spec_from_file_location("character_motion_fixture", ROOT / "tests/make_motion_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
MARKERS = [
    "mixamorig:Hips",
    "mixamorig:Head",
    "mixamorig:LeftHand",
    "mixamorig:RightHand",
    "mixamorig:LeftFoot",
    "mixamorig:RightFoot",
]
FRAMES = [1, 16, 31, 46, 61]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mesh_info(obj, rig):
    bone_names = set(rig.data.bones.keys())
    names = {g.index: g.name for g in obj.vertex_groups}
    weighted_vertices = sum(
        any(names.get(g.group) in bone_names and g.weight > 0 for g in v.groups) for v in obj.data.vertices
    )
    skin = any(m.type == "ARMATURE" and m.object == rig for m in obj.modifiers)
    return {
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "weighted_vertices": weighted_vertices,
        "has_armature_modifier": skin,
        "rigid_bone_parent": obj.parent == rig and obj.parent_type == "BONE",
        "nonempty_bone_groups": sorted(
            {
                names[g.group]
                for v in obj.data.vertices
                for g in v.groups
                if names.get(g.group) in bone_names and g.weight > 0
            }
        ),
    }


def sample_character(rig, meshes, indices, frames):
    previous, sub = bpy.context.scene.frame_current, bpy.context.scene.frame_subframe
    output = []
    try:
        for frame in frames:
            bpy.context.scene.frame_set(int(frame), subframe=float(frame) - int(frame))
            depsgraph = bpy.context.evaluated_depsgraph_get()
            bones = [tuple(rig.matrix_world @ rig.pose.bones[n].head) for n in MARKERS]
            sampled = {}
            for obj in meshes:
                evaluated = obj.evaluated_get(depsgraph)
                mesh = evaluated.to_mesh()
                try:
                    assert len(mesh.vertices) == len(obj.data.vertices), "Unexpected topology-changing modifier."
                    sampled[obj.name] = [tuple(evaluated.matrix_world @ mesh.vertices[i].co) for i in indices[obj.name]]
                finally:
                    evaluated.to_mesh_clear()
            output.append({"bones": bones, "meshes": sampled})
    finally:
        bpy.context.scene.frame_set(previous, subframe=sub)
    return output


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

    def import_range(match, scene_fps, expected_end):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = scene_fps
        assert bpy.context.scene.frame_end == 250
        source = folder / f"range_{scene_fps}_{match}.bvh"
        fixture.write_fixture(source)
        rig, file_fps = import_bvh(str(source), match_fps=match)
        start, end = rig.animation_data.action.frame_range
        assert abs(file_fps - 30) < 1e-6
        assert abs(start - 1) < 1e-6 and abs(end - expected_end) < 1e-4, (start, end)
        assert bpy.context.scene.frame_start == 1 and bpy.context.scene.frame_end == expected_end, (
            bpy.context.scene.frame_start,
            bpy.context.scene.frame_end,
        )
        fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
        assert abs((end - start) / fps - 2.0) < 1e-5
        return {
            "source_fps": file_fps,
            "scene_fps": fps,
            "action_range": [start, end],
            "scene_range": [bpy.context.scene.frame_start, bpy.context.scene.frame_end],
            "actual_animation_seconds": (end - start) / fps,
            "no_default_250_frame_tail": True,
        }

    def character_pipeline():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        asset = ROOT / "bvh_to_mixamo/templates/mixamo_default_white.fbx"
        asset_sha = digest(asset)
        assert asset_sha == TEMPLATE_SHA256[asset.name]
        source_path = folder / "character_source.bvh"
        fixture.write_fixture(source_path)
        source_sha = digest(source_path)
        source, _ = import_bvh(str(source_path), True)
        source = process_bones(source, get_default_mapping())
        target, imported_objects = import_character_template_fbx(str(asset))
        meshes = get_armature_meshes(target)
        assert meshes, "Bundled character did not produce bound meshes."
        before = {m.name: mesh_info(m, target) for m in meshes}
        assert sum(i["weighted_vertices"] for i in before.values()) > 0
        assert bpy.context.scene.render.fps / bpy.context.scene.render.fps_base == 30
        assert transfer_animation_with_constraints(source, target, ROOT_SCALE)
        assert tuple(target.animation_data.action.frame_range) == (1.0, 61.0)
        assert bpy.context.scene.frame_end == 61, ("Unexpected export tail", bpy.context.scene.frame_end)
        indices = {m.name: sorted({round(i * (len(m.data.vertices) - 1) / 63) for i in range(64)}) for m in meshes}
        expected = sample_character(target, meshes, indices, FRAMES)
        bone_names = set(target.data.bones.keys())
        object_names = [m.name for m in meshes]
        output = folder / "character_with_motion.fbx"
        export_armature_by_profile(target, str(output), EXPORT_PROFILE_MIXAMO, include_mesh=True)
        assert digest(asset) == asset_sha and digest(source_path) == source_sha
        assert output.is_file() and output.stat().st_size > 1000
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = 30
        bpy.ops.import_scene.fbx(filepath=str(output), use_anim=True, anim_offset=0.0, automatic_bone_orientation=False)
        rig = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
        roundtrip_meshes = get_armature_meshes(rig)
        assert set(rig.data.bones.keys()) == bone_names
        assert sorted(m.name for m in roundtrip_meshes) == sorted(object_names)
        after = {m.name: mesh_info(m, rig) for m in roundtrip_meshes}
        for name in before:
            assert after[name]["vertices"] == before[name]["vertices"], (name, before[name], after[name])
            assert after[name]["polygons"] == before[name]["polygons"]
            assert after[name]["weighted_vertices"] == before[name]["weighted_vertices"]
            assert after[name]["nonempty_bone_groups"] == before[name]["nonempty_bone_groups"]
            assert after[name]["has_armature_modifier"] == before[name]["has_armature_modifier"]
        start, end = rig.animation_data.action.frame_range
        assert round(end - start) + 1 == 61, (start, end)
        actual = sample_character(rig, roundtrip_meshes, indices, [start + f - 1 for f in FRAMES])
        bone_error = 0.0
        vertex_error = 0.0
        relative_motion = 0.0
        for old, new in zip(expected, actual):
            bone_error = max(bone_error, max(math.dist(a, b) for a, b in zip(old["bones"], new["bones"])))
            for name in object_names:
                vertex_error = max(
                    vertex_error, max(math.dist(a, b) for a, b in zip(old["meshes"][name], new["meshes"][name]))
                )
        for frame in expected[1:]:
            for name in object_names:
                for a, b in zip(expected[0]["meshes"][name], frame["meshes"][name]):
                    old_relative = [v - h for v, h in zip(a, expected[0]["bones"][0])]
                    new_relative = [v - h for v, h in zip(b, frame["bones"][0])]
                    relative_motion = max(relative_motion, math.dist(old_relative, new_relative))
        assert relative_motion > 1e-4, "No nonrigid/local-pose character motion was sampled."
        assert bone_error < 5e-5, bone_error
        assert vertex_error < 5e-5, vertex_error
        return {
            "asset_filename": asset.name,
            "asset_sha256": asset_sha,
            "native_character_bones": len(bone_names),
            "native_bound_mesh_count": len(meshes),
            "mesh_metadata_before": before,
            "mesh_metadata_after": after,
            "sampled_animation_frames": FRAMES,
            "vertex_samples_per_mesh_per_frame": {k: len(v) for k, v in indices.items()},
            "max_world_bone_marker_roundtrip_error_units": bone_error,
            "max_deformed_world_vertex_roundtrip_error_units": vertex_error,
            "nonrigid_root_relative_sampled_vertex_motion_units": relative_motion,
            "exported_action_range": [start, end],
            "mesh_export_enabled": True,
            "export_fbx_bytes": output.stat().st_size,
            "export_sha256": digest(output),
            "source_asset_and_synthetic_BVH_unchanged": True,
            "retarget_accuracy_or_original_performance_recovery_claim": False,
        }

    for name, function in [
        ("short_BVH_import_sets_actual_scene_range", lambda: import_range(True, 30, 61)),
        ("unmatched_scene60_source30_preserves_seconds", lambda: import_range(False, 60, 121)),
        ("bundled_character_ConstraintBake_mesh_FBX_roundtrip", character_pipeline),
    ]:
        run(name, function)
    report = {
        "blender_version": bpy.app.version_string,
        "passed": sum(c["passed"] for c in checks),
        "total": len(checks),
        "checks": checks,
        "scope": "Verified public bundled asset plus generated motion. Format, weights and sampled skin deformation preservation against the exported target; not cross-rig retarget accuracy or actual capture recovery.",
        "source_hashes": {
            name: digest(ROOT / "bvh_to_mixamo/core" / name)
            for name in ["bvh_parser.py", "retarget_engine.py", "export_profiles.py", "template_loader.py"]
        },
    }
    (folder / "verification.json").write_text(json.dumps(report, indent=2))
    assert report["passed"] == report["total"], [(c["id"], c.get("error")) for c in checks if not c["passed"]]


if __name__ == "__main__":
    main()
