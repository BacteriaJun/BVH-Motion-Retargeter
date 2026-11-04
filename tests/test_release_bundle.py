"""Install-archive regressions; all planted artifacts live in a temporary copy."""

import hashlib
import importlib.util
import re
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def release_module():
    spec = importlib.util.spec_from_file_location("isolated_release_builder", ROOT / "scripts/build_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "bvh_to_mixamo"
        shutil.copytree(ROOT / "bvh_to_mixamo", self.package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(ROOT / "LICENSE", self.root / "LICENSE")
        self.builder = release_module()
        self.builder.ROOT = self.root
        self.builder.PACKAGE = self.package
        self.builder.MANIFEST = self.package / "blender_manifest.toml"
        self.builder.ADDON_INFO = self.package / "addon_info.py"

    def tearDown(self):
        self.temporary.cleanup()

    def test_same_source_build_is_byte_deterministic_and_metadata_agrees(self):
        first = self.builder.build(self.root / "a.zip")
        second = self.builder.build(self.root / "b.zip")
        self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
        self.assertEqual(self.builder.manifest_version(), self.builder.addon_version())
        with zipfile.ZipFile(first) as z:
            self.assertIsNone(z.testzip())
            self.assertTrue(all(n.startswith("bvh_to_mixamo/") for n in z.namelist()))
            self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in z.infolist()))
            self.assertIn("bvh_to_mixamo/core/vmd_codec.py", z.namelist())
            self.assertEqual(z.read("bvh_to_mixamo/LICENSE.txt"), (self.root / "LICENSE").read_bytes())

    def test_private_capture_artifacts_never_enter_install_archive(self):
        planted = [
            "private_customer.vmd",
            "private_customer.bvh",
            "private_customer.blend",
            "private_customer.mp4",
            "private_customer.mov",
            "private_customer.zip",
            "private_customer_source.png",
        ]
        for name in planted:
            (self.package / name).write_bytes(b"PRIVATE TEST SENTINEL; no actual customer data")
        # A release can exclude these files or refuse unexpected package content.
        try:
            output = self.builder.build(self.root / "candidate.zip")
        except (ValueError, RuntimeError):
            return
        with zipfile.ZipFile(output) as z:
            present = sorted(set(z.namelist()) & {"bvh_to_mixamo/" + n for n in planted})
        self.assertEqual(present, [], "Private capture/test media were included in the installation archive")

    def test_unknown_python_reference_is_rejected(self):
        (self.package / "core/upstream_mmd_vmd_reference.py").write_text("# External reference; not product code")
        with self.assertRaises(RuntimeError):
            self.builder.build(self.root / "candidate.zip")
        self.assertFalse((self.root / "candidate.zip").exists())

    def test_bad_template_cannot_replace_an_existing_archive(self):
        output = self.root / "existing.zip"
        output.write_bytes(b"PREVIOUS ARCHIVE")
        template = self.package / "templates" / sorted(self.builder.REQUIRED_TEMPLATES)[0]
        template.write_bytes(b"TAMPERED TEMPLATE")
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.builder.build(output)
        self.assertEqual(output.read_bytes(), b"PREVIOUS ARCHIVE")
        self.assertFalse(list(self.root.glob(".bvh-release-*.tmp")))

    def test_duplicate_json_key_and_invalid_mapping_are_rejected(self):
        path = self.package / "presets/release_invalid.json"
        for text in [
            '{"mapping":{"Hips":"a","Hips":"b"}}',
            '{"mapping":{}}',
            '{"mapping":{"Hips":42}}',
            '{"mapping":{"Hips":"b"},"private_base64":"secret"}',
        ]:
            path.write_text(text)
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                self.builder.build(self.root / "candidate.zip")

    def test_unsafe_version_and_output_inside_package_are_rejected(self):
        with self.assertRaises(RuntimeError):
            self.builder.build(self.package / "nested.zip")
        self.assertFalse((self.package / "nested.zip").exists())
        text = self.builder.MANIFEST.read_text()
        text = re.sub(r"^version\s*=.*$", 'version = "../other/output"', text, flags=re.MULTILINE)
        self.builder.MANIFEST.write_text(text)
        with self.assertRaises(RuntimeError):
            self.builder.build(self.root / "candidate.zip")

    def test_symlink_cannot_exfiltrate_an_external_file(self):
        external = self.root / "customer-secret.bin"
        external.write_bytes(b"SYNTHETIC PRIVATE CONTENT")
        (self.package / "core/upstream_reference.py").symlink_to(external)
        with self.assertRaises(RuntimeError):
            self.builder.build(self.root / "candidate.zip")
        self.assertEqual(external.read_bytes(), b"SYNTHETIC PRIVATE CONTENT")

    def test_archive_write_failure_preserves_previous_destination(self):
        output = self.root / "previous.zip"
        output.write_bytes(b"PREVIOUS ARCHIVE")
        with mock.patch.object(zipfile.ZipFile, "writestr", side_effect=OSError("Injected archive write failure")):
            with self.assertRaises(OSError):
                self.builder.build(output)
        self.assertEqual(output.read_bytes(), b"PREVIOUS ARCHIVE")
        self.assertFalse(list(self.root.glob(".bvh-release-*.tmp")))

    def test_actual_package_has_no_external_reference_module_or_private_motion(self):
        paths = self.builder.package_files()
        names = [str(p.relative_to(self.package)) for p in paths]
        forbidden = {".vmd", ".bvh", ".blend", ".mp4", ".mov", ".zip"}
        self.assertFalse([n for n in names if Path(n).suffix.lower() in forbidden])
        self.assertFalse([n for n in names if "upstream_mmd" in n or "reference_vmd" in n])
        self.assertFalse([n for n in names if "__pycache__" in Path(n).parts])


if __name__ == "__main__":
    unittest.main()
