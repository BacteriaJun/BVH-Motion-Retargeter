"""Native black/white assets and saved Scene preset migration."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bvh_to_mixamo as addon
from bvh_to_mixamo.core.template_loader import (
    TEMPLATE_PRESET_BUILTIN_BLACK,
    TEMPLATE_PRESET_BUILTIN_WHITE,
    TEMPLATE_PRESET_CUSTOM_FBX,
    TEMPLATE_REGISTRY,
    get_template_fbx_path,
    migrate_legacy_template_selection,
)
from scripts.fetch_templates import TEMPLATE_SHA256


def make_legacy_native_fixture(output):
    # Reproduce the old static EnumProperty through RNA, rather than assuming
    # registered properties are visible through Scene's custom-ID mapping.
    identifiers = [
        "BUILTIN_DEFAULT_CHARACTER",
        TEMPLATE_PRESET_BUILTIN_WHITE,
        "BUILTIN_PINK_CHARACTER",
        "BUILTIN_PURPLE_CHARACTER",
        TEMPLATE_PRESET_BUILTIN_BLACK,
        "BUILTIN_GREEN_CHARACTER",
        TEMPLATE_PRESET_CUSTOM_FBX,
    ]
    legacy_items = [(identifier, identifier, "", number) for number, identifier in enumerate(identifiers)]
    bpy.types.Scene.bvh_template_preset = bpy.props.EnumProperty(
        items=legacy_items, default="BUILTIN_DEFAULT_CHARACTER"
    )
    bpy.types.Scene.bvh_custom_template_fbx_path = bpy.props.StringProperty()
    expected = {}
    for identifier in identifiers:
        scene = bpy.data.scenes.new("Native_legacy_" + identifier)
        scene.bvh_template_preset = identifier
        scene.bvh_custom_template_fbx_path = "keep native path " + identifier
        expected[scene.name] = (
            identifier
            if identifier in {TEMPLATE_PRESET_BUILTIN_WHITE, TEMPLATE_PRESET_BUILTIN_BLACK, TEMPLATE_PRESET_CUSTOM_FBX}
            else TEMPLATE_PRESET_BUILTIN_WHITE
        )
    saved = output / "native_legacy_template_choices.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(saved))
    del bpy.types.Scene.bvh_template_preset
    del bpy.types.Scene.bvh_custom_template_fbx_path
    return saved, expected


def assert_native_legacy_preserved(expected):
    for name, identifier in expected.items():
        scene = bpy.data.scenes[name]
        assert scene.bvh_template_preset == identifier, (name, scene.bvh_template_preset, identifier)
        assert scene.bvh_custom_template_fbx_path == "keep native path " + name.removeprefix("Native_legacy_")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    args.output.mkdir(parents=True, exist_ok=True)
    checks = {}
    assets = []
    assert set(TEMPLATE_REGISTRY) == {TEMPLATE_PRESET_BUILTIN_WHITE, TEMPLATE_PRESET_BUILTIN_BLACK}
    for name in ["mixamo_default_white.fbx", "mixamo_default_black.fbx"]:
        path = ROOT / "bvh_to_mixamo/templates" / name
        original = hashlib.sha256(path.read_bytes()).hexdigest()
        assert original == TEMPLATE_SHA256[name]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        assert bpy.ops.import_scene.fbx(filepath=str(path)) == {"FINISHED"}
        rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        assert len(rigs) == 1 and len(meshes) == 2
        assert "mixamorig:Hips" in rigs[0].data.bones
        assert all(mesh.vertex_groups for mesh in meshes)
        assert sum(len(mesh.data.vertices) for mesh in meshes) == 27850
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original
        assets.append(
            {
                "filename": name,
                "bones": len(rigs[0].data.bones),
                "meshes": len(meshes),
                "vertices": 27850,
                "sha256": original,
            }
        )
    checks["both_black_white_assets_native_import_and_weights"] = True
    legacy_native_path, expected_native = make_legacy_native_fixture(args.output)
    addon.register()
    try:
        assert_native_legacy_preserved(expected_native)
        bpy.ops.wm.open_mainfile(filepath=str(legacy_native_path))
        assert_native_legacy_preserved(expected_native)
        scenes = []
        for value in [0, 2, 3, 5]:
            scene = bpy.data.scenes.new("Legacy_numeric_" + str(value))
            scene["bvh_template_preset"] = value
            scene.bvh_custom_template_fbx_path = "keep custom path " + str(value)
            scenes.append(scene)
        report = migrate_legacy_template_selection(scenes)
        assert report["changed_scene_count"] == 4
        for scene in scenes:
            assert scene.bvh_template_preset == TEMPLATE_PRESET_BUILTIN_WHITE
            assert scene.get("bvh_template_preset") in {1, None}
            assert scene.bvh_custom_template_fbx_path.startswith("keep custom path ")
            assert (
                Path(get_template_fbx_path(type("Context", (), {"scene": scene})())).name == "mixamo_default_white.fbx"
            )
        checks["retired_numeric_choices_migrate_to_white_and_preserve_paths"] = True
        legacy = [
            "BUILTIN_DEFAULT_CHARACTER",
            "BUILTIN_PINK_CHARACTER",
            "BUILTIN_PURPLE_CHARACTER",
            "BUILTIN_GREEN_CHARACTER",
        ]
        for identifier in legacy:
            scene = bpy.data.scenes.new(identifier)
            scene["bvh_template_preset"] = identifier
            migrate_legacy_template_selection([scene])
            assert scene.bvh_template_preset == TEMPLATE_PRESET_BUILTIN_WHITE
        checks["retired_string_identifiers_migrate_to_white"] = True
        current = {1: TEMPLATE_PRESET_BUILTIN_WHITE, 4: TEMPLATE_PRESET_BUILTIN_BLACK, 6: TEMPLATE_PRESET_CUSTOM_FBX}
        for number, identifier in current.items():
            scene = bpy.data.scenes.new("Keep_" + identifier)
            scene["bvh_template_preset"] = number
            scene.bvh_custom_template_fbx_path = "custom character.fbx"
            assert migrate_legacy_template_selection([scene])["changed_scene_count"] == 0
            assert scene.bvh_template_preset == identifier
            assert scene.bvh_custom_template_fbx_path == "custom character.fbx"
            if "bvh_template_preset" in scene:
                del scene["bvh_template_preset"]
            scene["bvh_template_preset"] = identifier
            migrate_legacy_template_selection([scene])
            assert scene.bvh_template_preset == identifier and scene.get("bvh_template_preset") in {number, None}
        checks["white_black_custom_current_choices_and_string_storage_preserved"] = True
        loaded = bpy.data.scenes.new("Load_Legacy_Pink")
        loaded["bvh_template_preset"] = 2
        loaded.bvh_custom_template_fbx_path = "keep after reopening.fbx"
        saved = args.output / "legacy_template_choice.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(saved))
        assert loaded["bvh_template_preset"] == 2
        bpy.ops.wm.open_mainfile(filepath=str(saved))
        loaded = bpy.data.scenes["Load_Legacy_Pink"]
        assert loaded.bvh_template_preset == TEMPLATE_PRESET_BUILTIN_WHITE
        assert loaded.bvh_custom_template_fbx_path == "keep after reopening.fbx"
        loaded.bvh_template_preset = TEMPLATE_PRESET_BUILTIN_BLACK
        migrate_legacy_template_selection([loaded])
        assert loaded.bvh_template_preset == TEMPLATE_PRESET_BUILTIN_BLACK
        bpy.ops.wm.save_as_mainfile(filepath=str(saved))
        bpy.ops.wm.open_mainfile(filepath=str(saved))
        loaded = bpy.data.scenes["Load_Legacy_Pink"]
        assert loaded.bvh_template_preset == TEMPLATE_PRESET_BUILTIN_BLACK
        assert loaded.bvh_custom_template_fbx_path == "keep after reopening.fbx"
        checks["saved_project_load_post_migrates_retired_preset"] = True
    finally:
        addon.unregister()
    result = {
        "blender_version": bpy.app.version_string,
        "all_passed": all(checks.values()),
        "checks": checks,
        "assets": assets,
        "scope": "Two shipped FBX assets and actual Scene enum-storage/load migration.",
    }
    (args.output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
