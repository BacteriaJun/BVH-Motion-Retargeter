"""Independent add-on language, data stability, persistence and native RNA checks.

blender --background --factory-startup --disable-autoexec --python-exit-code 1
        --python FILE -- --output NEW_DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bvh_to_mixamo as addon
from bvh_to_mixamo.core import i18n
from bvh_to_mixamo.ui.panel import MIXAMO_PT_panel


class Layout:
    def __init__(self, rows=None):
        self.rows = [] if rows is None else rows

    def box(self):
        return Layout(self.rows)

    def row(self, **kwargs):
        return Layout(self.rows)

    def column(self, **kwargs):
        return Layout(self.rows)

    def separator(self):
        pass

    def label(self, **kwargs):
        self.rows.append(("label", kwargs.get("text", ""), kwargs))

    def prop(self, data, name, **kwargs):
        assert hasattr(data, name), name
        self.rows.append(("prop", kwargs.get("text", ""), kwargs))

    def operator(self, identifier, **kwargs):
        module, name = identifier.split(".")
        getattr(getattr(bpy.ops, module), name).get_rna_type()
        self.rows.append(("operator", kwargs.get("text", ""), kwargs))
        return SimpleNamespace()


def prefs_snapshot():
    view = bpy.context.preferences.view
    return {
        name: getattr(view, name)
        for name in ["language", "use_translate_interface", "use_translate_tooltips", "use_translate_new_dataname"]
    }


def panel_texts():
    layout = Layout()
    MIXAMO_PT_panel.draw(SimpleNamespace(layout=layout), bpy.context)
    for kind, _text, kwargs in layout.rows:
        assert kwargs.get("translate") is False, (kind, kwargs)
    return [text for _kind, text, _kwargs in layout.rows]


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    original_prefs = prefs_snapshot()
    checks = {}
    initial_properties = {name for name in dir(bpy.types.Scene) if name.startswith("bvh_")}
    addon.register()
    scene = bpy.context.scene
    scene.bvh_input_path = "/用户/原始素材/Frame.bvh"
    scene.bvh_last_output_armature = "Frame / 角色_A"
    scene.bvh_cleanup_strength = 0.73
    scene.bvh_template_preset = "BUILTIN_BLACK_CHARACTER"
    scene.bvh_root_motion_mode = "IN_PLACE"
    scene.bvh_target_skeleton = "UE4_BASIC"
    stable = {
        name: getattr(scene, name)
        for name in [
            "bvh_input_path",
            "bvh_last_output_armature",
            "bvh_cleanup_strength",
            "bvh_template_preset",
            "bvh_root_motion_mode",
            "bvh_target_skeleton",
        ]
    }
    enum_ids = {key: [(item[0], item[-1]) for item in source] for key, source in i18n._ENUM_TABLES.items()}
    first_items = {}
    for repeat in range(6):
        for language in ["zh_CN", "en_US"]:
            scene.bvh_ui_language = language
            assert prefs_snapshot() == original_prefs
            for name, value in stable.items():
                assert getattr(scene, name) == value, (name, language)
            for key, callback in i18n._ENUM_CALLBACKS.items():
                items = callback(scene, bpy.context)
                assert [(item[0], item[-1]) for item in items] == enum_ids[key]
                if repeat == 0:
                    first_items[key, language] = items
                else:
                    assert items is first_items[key, language], (key, language)
            assert bpy.app.translations.pgettext("Denoise Strength", i18n.CONTEXT) == (
                "去抖强度" if language == "zh_CN" else "Denoise Strength"
            )
            for source in ["VMD", "BVH"]:
                scene.bvh_source_format = source
                for target in ["MIXAMO", "UE4_BASIC", "UE5_BASIC", "VRM_BODY"]:
                    scene.bvh_target_skeleton = target
                    for bind in ["CREATE", "BIND_SELECTED", "BIND_TEMPLATE"]:
                        scene.bvh_bind_mode = bind
                        for export_mode in ["PRESERVE", "NEW_FK"]:
                            scene.bvh_vmd_export_mode = export_mode
                            texts = panel_texts()
                            expected = "1. VMD 源动作" if language == "zh_CN" else "1. VMD Source"
                            if source == "BVH":
                                expected = "1. 源动作" if language == "zh_CN" else "1. Source Motion"
                            assert expected in texts, (language, source, texts)
                            assert "Language / 界面语言" in texts
                            assert not any(text.endswith(" RC") for text in texts)
                            if source == "BVH":
                                assert (
                                    "上次输出：Frame / 角色_A" if language == "zh_CN" else "Last output: Frame / 角色_A"
                                ) in texts
            # Restore enum values after exercising conditional UI branches.
            for name, value in stable.items():
                setattr(scene, name, value)
    checks["language_switch_keeps_data_and_global_blender_preferences"] = True
    checks["all_main_panel_branches_in_both_languages"] = True
    checks["enum_identifiers_values_and_cached_strings_are_stable"] = True
    assert bpy.types.Scene.bl_rna.properties["bvh_cleanup_strength"].translation_context == i18n.CONTEXT
    # Native Blender translation switches still govern its own RNA tooltips.
    # The panel proxy above uses already translated text with translate=False.
    checks["native_rna_translation_context"] = True
    scene.bvh_ui_language = "zh_CN"
    assert (
        i18n.tr("Non-finite bone transform at frame 6.250: mixamorig:LeftFoot")
        == "第 6.250 帧的骨骼变换无效：mixamorig:LeftFoot"
    )
    reports = []
    i18n.translated_report(
        bpy.context,
        lambda level, text: reports.append((level, text)),
        {"ERROR"},
        "Processing failed: An Action is required.",
    )
    assert reports == [({"ERROR"}, "处理失败：需要一个动作。")]
    for operator in addon.operator_classes:
        assert operator.bl_translation_context == i18n.CONTEXT
        assert operator.description(bpy.context, None) == i18n.tr(
            operator.bl_description if hasattr(operator, "bl_description") else operator.bl_label
        )
    checks["operator_descriptions_reports_and_dynamic_core_errors"] = True
    saved = output / "language_scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(saved))
    scene.bvh_ui_language = "en_US"
    bpy.ops.wm.open_mainfile(filepath=str(saved))
    scene = bpy.context.scene
    assert scene.bvh_ui_language == "zh_CN"
    assert bpy.app.translations.pgettext("Denoise Strength", i18n.CONTEXT) == "去抖强度"
    for name, value in stable.items():
        assert getattr(scene, name) == value, name
    assert prefs_snapshot() == original_prefs
    checks["language_saved_and_restored_with_project_without_losing_settings"] = True
    # AUTO reads the actual current Blender preference; fake locale branches are covered by pure tests.
    scene.bvh_ui_language = "AUTO"
    expected_auto = "zh_CN" if str(bpy.context.preferences.view.language).lower().startswith("zh") else "en_US"
    assert i18n.language() == expected_auto
    checks["auto_follows_blender_preference"] = True
    for repeat in range(3):
        addon.unregister()
        assert {name for name in dir(bpy.types.Scene) if name.startswith("bvh_")} == initial_properties
        assert addon._on_project_load not in bpy.app.handlers.load_post
        assert not i18n._REGISTERED
        addon.register()
        assert bpy.app.handlers.load_post.count(addon._on_project_load) == 1
        scene = bpy.context.scene
        scene.bvh_ui_language = "zh_CN" if repeat % 2 else "en_US"
        assert prefs_snapshot() == original_prefs
    addon.unregister()
    checks["repeated_registration_has_no_rna_handler_or_translation_leaks"] = True
    report = {
        "blender": bpy.app.version_string,
        "checks": checks,
        "catalog_entries": len(i18n.TRANSLATIONS),
        "cached_enum_tables": len(i18n._ENUM_CACHE),
        "global_preferences_unchanged": prefs_snapshot() == original_prefs,
        "native_translation_preferences": original_prefs,
    }
    (output / "i18n_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    print("I18N_TEST_OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    main(args.output)
