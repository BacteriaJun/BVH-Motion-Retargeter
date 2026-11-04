"""Template preparation contracts with synthetic payloads in temporary folders."""

import hashlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TemplateAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / "templates"
        self.output.mkdir()
        self.fetch = module_at("isolated_template_fetch", ROOT / "scripts/fetch_templates.py")
        self.fetch.OUTPUT_DIR = self.output

    def tearDown(self):
        self.temp.cleanup()

    def test_default_is_white_and_required_assets_are_exactly_black_white(self):
        paths = module_at("isolated_template_paths", ROOT / "bvh_to_mixamo/core/paths.py")
        self.assertEqual(Path(paths.get_default_template_fbx_path()).name, "mixamo_default_white.fbx")
        self.assertEqual(set(self.fetch.TEMPLATE_SHA256), {"mixamo_default_white.fbx", "mixamo_default_black.fbx"})

    def test_verified_cache_avoids_network(self):
        values = {"mixamo_default_white.fbx": b"white fixture", "mixamo_default_black.fbx": b"black fixture"}
        self.fetch.TEMPLATE_SHA256 = {name: hashlib.sha256(value).hexdigest() for name, value in values.items()}
        for name, value in values.items():
            (self.output / name).write_bytes(value)
        with mock.patch.object(
            self.fetch.urllib.request, "urlopen", side_effect=AssertionError("Unexpected network call")
        ):
            self.fetch.main()
        for name, value in values.items():
            self.assertEqual((self.output / name).read_bytes(), value)

    def test_retired_unmodified_assets_removed_but_custom_data_preserved(self):
        exact = self.output / "retired.fbx"
        exact.write_bytes(b"old release fixture")
        custom = self.output / "custom.fbx"
        custom.write_bytes(b"user character fixture")
        self.fetch.RETIRED_TEMPLATE_SHA256 = {exact.name: hashlib.sha256(exact.read_bytes()).hexdigest()}
        self.fetch.retire_duplicate_templates()
        self.assertFalse(exact.exists())
        self.assertEqual(custom.read_bytes(), b"user character fixture")
        exact.write_bytes(b"locally changed fixture")
        with self.assertRaises(RuntimeError):
            self.fetch.retire_duplicate_templates()
        self.assertEqual(exact.read_bytes(), b"locally changed fixture")

    def test_bad_staged_template_does_not_replace_existing_output(self):
        expected = {"mixamo_default_white.fbx": b"white fixture", "mixamo_default_black.fbx": b"black fixture"}
        self.fetch.TEMPLATE_SHA256 = {name: hashlib.sha256(value).hexdigest() for name, value in expected.items()}
        white = self.output / "mixamo_default_white.fbx"
        white.write_bytes(expected[white.name])
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, value in expected.items():
                archive.writestr("bvh_to_mixamo/templates/" + name, b"tampered fixture" if "black" in name else value)
        payload = stream.getvalue()
        self.fetch.ARCHIVE_SHA256 = hashlib.sha256(payload).hexdigest()
        with mock.patch.object(self.fetch.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
            with self.assertRaises(RuntimeError):
                self.fetch.main()
        self.assertEqual(white.read_bytes(), expected[white.name])
        self.assertFalse((self.output / "mixamo_default_black.fbx").exists())


if __name__ == "__main__":
    unittest.main()
