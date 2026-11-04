"""Install the built ZIP in isolated Blender user directories.

Set BLENDER_USER_CONFIG and BLENDER_USER_SCRIPTS to fresh subdirectories of the
--output directory BEFORE starting Blender. Run --factory-startup and
--disable-autoexec; this test refuses ordinary user configuration paths.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
import traceback
import zipfile
from pathlib import Path

import bpy


def run(package: Path, output: Path):
    package = package.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = os.environ.get("BLENDER_USER_CONFIG")
    scripts = os.environ.get("BLENDER_USER_SCRIPTS")
    if not config or not scripts:
        raise ValueError("Set isolated BLENDER_USER_CONFIG and BLENDER_USER_SCRIPTS before launching Blender")
    for value in (config, scripts):
        if not Path(value).resolve().is_relative_to(output):
            raise ValueError("Isolated Blender user directories must be inside this test output directory")
    for value in (config, scripts):
        if not Path(value).is_dir():
            raise ValueError("Create isolated user directories before launching Blender; startup fallback is not allowed")
    actual_scripts = Path(bpy.utils.user_resource("SCRIPTS")).resolve()
    actual_config = Path(bpy.utils.user_resource("CONFIG")).resolve()
    if actual_scripts != Path(scripts).resolve() or actual_config != Path(config).resolve():
        raise ValueError("Blender resolved a non-isolated user resource path; installation refused before writing")
    if "bvh_to_mixamo" in sys.modules:
        raise AssertionError("Addon was already imported; installed-package isolation cannot be established")
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert all(n.startswith("bvh_to_mixamo/") and ".." not in Path(n).parts for n in names)
        assert "bvh_to_mixamo/core/vmd_codec.py" in names
        assert "bvh_to_mixamo/core/vmd_blender.py" in names
    checks = {"install_ZIP_CRC_and_expected_package_root": True}
    source_hash = hashlib.sha256(package.read_bytes()).hexdigest()
    props_before = {p for p in dir(bpy.types.Scene) if p.startswith("bvh_")}
    result = bpy.ops.preferences.addon_install(filepath=str(package), overwrite=False)
    assert "FINISHED" in result, result
    import addon_utils

    discovered = next(module for module in addon_utils.modules(refresh=True) if module.__name__ == "bvh_to_mixamo")
    assert discovered.bl_info["name"] == "BVH Motion Retargeter"
    assert discovered.bl_info["version"] == (4, 0, 0)
    checks["actual_preferences_addon_install"] = True
    result = bpy.ops.preferences.addon_enable(module="bvh_to_mixamo")
    assert "FINISHED" in result, result
    addon = importlib.import_module("bvh_to_mixamo")
    installed = Path(addon.__file__).resolve()
    assert installed.is_relative_to(Path(scripts).resolve()), installed
    assert bpy.context.preferences.addons.get("bvh_to_mixamo") is not None
    introduced = {p for p in dir(bpy.types.Scene) if p.startswith("bvh_")} - props_before
    assert len(introduced) >= 30
    # Background scripts do not tick UI timers. Exercise its normal-context
    # callback explicitly, then remove the timer as Blender would on None.
    if bpy.app.timers.is_registered(addon._deferred_initialize):
        assert addon._deferred_initialize() is None
        bpy.app.timers.unregister(addon._deferred_initialize)
    checks["actual_addon_enable_from_isolated_installed_files"] = True
    from bvh_to_mixamo.core import vmd_codec as codec

    motion = codec.Motion(
        model_name="Install test",
        bones=[codec.BoneFrame("センター", 0), codec.BoneFrame("センター", 5, (0.1, 0.0, 0.0))],
        morphs=[codec.MorphFrame("笑い", 2, 0.3)],
    )
    source = output / "installed_source.vmd"
    codec.write_vmd(source, motion, overwrite=True)
    scene = bpy.context.scene
    scene.bvh_source_format = "VMD"
    scene.bvh_vmd_import_mode = "PREVIEW"
    scene.bvh_vmd_input_path = str(source)
    assert "FINISHED" in bpy.ops.bvh.import_vmd()
    rig = bpy.context.view_layer.objects.active
    assert rig and rig.type == "ARMATURE" and rig.animation_data.action
    scene.bvh_vmd_output_path = str(output / "installed_preserved.vmd")
    scene.bvh_export_overwrite = True
    scene.bvh_vmd_export_mode = "PRESERVE"
    assert "FINISHED" in bpy.ops.bvh.export_vmd()
    assert (output / "installed_preserved.vmd").read_bytes() == source.read_bytes()
    checks["installed_VMD_import_export_bytes_preserved"] = True
    saved = bpy.ops.wm.save_userpref()
    assert "FINISHED" in saved
    assert (Path(config) / "userpref.blend").is_file()
    checks["preferences_saved_only_in_isolated_config"] = True
    assert "FINISHED" in bpy.ops.preferences.addon_disable(module="bvh_to_mixamo")
    assert bpy.context.preferences.addons.get("bvh_to_mixamo") is None
    assert not (introduced & set(dir(bpy.types.Scene)))
    assert all(not cls.is_registered for cls in addon.classes)
    assert not bpy.app.timers.is_registered(addon._deferred_initialize)
    assert addon._on_project_load not in bpy.app.handlers.load_post
    checks["actual_addon_disable_unregisters_classes_and_properties"] = True
    assert "FINISHED" in bpy.ops.preferences.addon_enable(module="bvh_to_mixamo")
    assert "FINISHED" in bpy.ops.preferences.addon_disable(module="bvh_to_mixamo")
    assert not bpy.app.timers.is_registered(addon._deferred_initialize)
    checks["installed_enable_disable_second_cycle"] = True
    assert hashlib.sha256(package.read_bytes()).hexdigest() == source_hash
    checks["input_install_ZIP_unchanged"] = True
    report = {
        "blender_version": bpy.app.version_string,
        "addon_version": addon.VERSION,
        "all_passed": all(checks.values()),
        "checks": checks,
        "package_sha256": source_hash,
        "package": str(package),
        "installed_module": str(installed),
        "isolated_config": config,
        "isolated_scripts": scripts,
        "scope": "Actual legacy ZIP install/enable and VMD operator smoke. Isolated preferences only; no user default configuration or external service modified.",
    }
    (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    try:
        run(args.zip, args.output)
    except Exception:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "failure.json").write_text(
            json.dumps({"error": traceback.format_exc(), "blender_version": bpy.app.version_string}, indent=2), encoding="utf-8"
        )
        raise
