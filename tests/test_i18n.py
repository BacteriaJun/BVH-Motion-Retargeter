"""Catalog and message formatting checks independent of Blender."""

import ast
import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
# Give the two leaf modules a package without importing the Blender add-on.
PACKAGE = "_bvh_i18n_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "bvh_to_mixamo/core")]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.i18n", ROOT / "bvh_to_mixamo/core/i18n.py")
i18n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i18n)


def context(language="zh_CN", blender_language="en_US"):
    return SimpleNamespace(
        scene=SimpleNamespace(bvh_ui_language=language),
        preferences=SimpleNamespace(view=SimpleNamespace(language=blender_language)),
    )


class TranslationTests(unittest.TestCase):
    def test_auto_language_and_unknown_locale_fallback(self):
        for locale in ["zh_CN", "zh_HANS", "zh_TW"]:
            self.assertEqual(i18n.language(context("AUTO", locale)), "zh_CN")
        for locale in ["en_US", "fr_FR", "ja_JP", "unknown"]:
            self.assertEqual(i18n.language(context("AUTO", locale)), "en_US")
        self.assertEqual(i18n.language(context("zh_CN", "en_US")), "zh_CN")
        self.assertEqual(i18n.language(context("en_US", "zh_CN")), "en_US")

    def test_dynamic_errors_preserve_bone_names_paths_frames_and_precision(self):
        ctx = context()
        path = '/动画/Frame/mixamorig:LeftFoot["rotation"].vmd'
        result = i18n.tr(f"Non-finite animation value at frame 12.500: {path}", ctx)
        self.assertEqual(result, f"第 12.500 帧的动画数值无效：{path}")
        self.assertEqual(i18n.tr(result, context("en_US")), f"Non-finite animation value at frame 12.500: {path}")
        self.assertEqual(
            i18n.tr("Proposed root correction 0.0300L exceeds the 0.0250L budget.", ctx),
            "预计根位移修正 0.0300L 超过 0.0250L 上限。",
        )
        self.assertEqual(
            i18n.tr("VMD bone name exceeds 15 CP932 bytes: Frame", ctx), "VMD 骨名超过 15 个 CP932 字节：Frame"
        )

    def test_nested_errors_and_field_glossary(self):
        self.assertEqual(
            i18n.tr("Processing failed: Bone name must not be empty", context()), "处理失败：骨骼名称 不能为空"
        )
        self.assertEqual(
            i18n.tr("Processing failed: 骨骼名称 不能为空", context("en_US")),
            "Processing failed: Bone name must not be empty",
        )
        self.assertEqual(i18n.tr("Truncated Bone rotation at byte 37", context()), "骨骼旋转 在第 37 字节处不完整")

    def test_literal_braces_unknown_text_and_explicit_values(self):
        source = "mapping must be a nonempty {VMD name: Blender bone name} object"
        translated = i18n.tr(source, context())
        self.assertNotIn("{", translated)
        self.assertEqual(i18n.tr(translated, context("en_US")), source)
        self.assertEqual(i18n.tr("Uncatalogued {bone} 文件", context()), "Uncatalogued {bone} 文件")
        self.assertEqual(i18n.tr("Selected target: {name}", context(), name="Frame"), "所选目标：Frame")
        self.assertEqual(i18n.tr("Selected target: {name}", context("en_US"), name="Frame"), "Selected target: Frame")

    def test_chinese_core_errors_are_readable_in_english(self):
        self.assertEqual(
            i18n.tr("mapping字段必须是JSON对象/dict", context("en_US")), "The mapping field must be a JSON object."
        )

    def test_report_keeps_levels_and_payload_values(self):
        reports = []
        i18n.translated_report(
            context(),
            lambda levels, message: reports.append((levels, message)),
            {"WARNING"},
            "Root discontinuity candidates: [2, 15, 30]",
        )
        self.assertEqual(reports, [({"WARNING"}, "根运动跳变候选帧：[2, 15, 30]")])

    def test_every_visible_property_panel_and_operator_string_is_catalogued(self):
        texts = set()
        paths = [
            ROOT / "bvh_to_mixamo/properties.py",
            ROOT / "bvh_to_mixamo/ui/panel.py",
            *(ROOT / "bvh_to_mixamo/operators").glob("*.py"),
        ]
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.keyword)
                    and node.arg in {"name", "description", "text"}
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    texts.add(node.value.value)
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Constant)
                    and any(
                        isinstance(target, ast.Name) and target.id in {"bl_label", "bl_description"}
                        for target in node.targets
                    )
                ):
                    texts.add(node.value.value)
                if isinstance(node, ast.keyword) and node.arg == "items" and isinstance(node.value, ast.List):
                    for item in node.value.elts:
                        if isinstance(item, ast.Tuple):
                            texts.update(
                                value.value
                                for value in item.elts[1:3]
                                if isinstance(value, ast.Constant) and isinstance(value.value, str)
                            )
        fixed_language_controls = {
            "",
            "Language / 界面语言",
            "Auto / 自动",
            "English",
            "简体中文",
            "Follow Blender language / 跟随 Blender 语言",
            "Use the English interface",
            "使用简体中文界面",
        }
        technical_names = {"VMD", "BVH", "Mixamo", "Mixamo FBX", "UE4 FBX", "UE5 FBX"}
        self.assertEqual(texts - fixed_language_controls - technical_names - i18n.TRANSLATIONS.keys(), set())
        for source in texts - fixed_language_controls - technical_names:
            self.assertRegex(i18n.TRANSLATIONS[source], r"[\u3400-\u9fff]")

    def test_core_catalog_is_loaded(self):
        self.assertGreaterEqual(len(i18n.ERROR_TRANSLATIONS), 184)
        for source, target in i18n.ERROR_TRANSLATIONS.items():
            self.assertEqual(i18n.TRANSLATIONS[source], target)

    def test_template_placeholders_are_consistent(self):
        def fields(value):
            return set(re.findall(r"\{([A-Za-z_][A-Za-z_0-9]*)(?::[^{}]+)?\}", value))

        for source, target in i18n.TRANSLATIONS.items():
            self.assertEqual(fields(source), fields(target), source)


if __name__ == "__main__":
    unittest.main()
