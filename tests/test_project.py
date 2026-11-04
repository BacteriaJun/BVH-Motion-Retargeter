import ast
import hashlib
import json
import re
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "bvh_to_mixamo"


def read_addon_version() -> str:
    path = PACKAGE / "addon_info.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ADDON_VERSION" for target in node.targets
        ):
            return ".".join(str(part) for part in ast.literal_eval(node.value))
    raise AssertionError("ADDON_VERSION was not found")


def read_manifest_string(key: str) -> str:
    text = (PACKAGE / "blender_manifest.toml").read_text(encoding="utf-8")
    match = re.search(rf'^{re.escape(key)}\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not match:
        raise AssertionError(f"{key} was not found in blender_manifest.toml")
    return match.group(1)


class ProjectMetadataTests(unittest.TestCase):
    def test_manifest_matches_addon_metadata(self) -> None:
        manifest_text = (PACKAGE / "blender_manifest.toml").read_text(encoding="utf-8")
        self.assertEqual(read_manifest_string("version"), read_addon_version())
        self.assertEqual(read_manifest_string("id"), "bvh_to_mixamo")
        self.assertIn('license = ["SPDX:MIT"]', manifest_text)
        entrypoint = ast.parse((PACKAGE / "__init__.py").read_text())
        metadata = next(
            ast.literal_eval(node.value)
            for node in entrypoint.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets)
        )
        self.assertEqual(metadata, runpy.run_path(str(PACKAGE / "addon_info.py"))["bl_info"])

    def test_presets_are_valid_mapping_objects(self) -> None:
        preset_paths = sorted((PACKAGE / "presets").glob("*.json"))
        self.assertGreaterEqual(len(preset_paths), 4)

        for path in preset_paths:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                mapping = data.get("mapping", data)
                self.assertIsInstance(mapping, dict)
                self.assertTrue(mapping)
                self.assertTrue(all(isinstance(key, str) for key in mapping))
                self.assertTrue(all(isinstance(value, str) for value in mapping.values()))

    def test_default_mapping_contains_hips(self) -> None:
        path = PACKAGE / "presets" / "default_mixamo_mapping.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping = data.get("mapping", data)
        self.assertEqual(mapping["Hips"], "mixamorig:Hips")

    def test_bundled_templates_are_present(self) -> None:
        from scripts.fetch_templates import TEMPLATE_SHA256

        templates = sorted((PACKAGE / "templates").glob("*.fbx"))
        self.assertEqual({p.name for p in templates}, {"mixamo_default_white.fbx", "mixamo_default_black.fbx"})
        for path in templates:
            with self.subTest(path=path.name):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(digest, TEMPLATE_SHA256[path.name])


if __name__ == "__main__":
    unittest.main()
