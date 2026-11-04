"""Mocked CI runtime integrity tests; no Linux download or GitHub run is performed."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tested_fetch_blender", ROOT / "scripts/fetch_blender.py")
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)


class FakeResponse(io.BytesIO):
    def __init__(self, payload, url, declared=None):
        super().__init__(payload)
        self.url = url
        self.headers = {} if declared is None else {"Content-Length": declared}

    def geturl(self):
        return self.url


def runtime_tar(root, extras=()):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        directory = tarfile.TarInfo(root)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        info = tarfile.TarInfo(root + "/blender")
        content = b"\x7fELFsynthetic CI test; not executable Blender code"
        info.size = len(content)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(content))
        for info, content in extras:
            archive.addfile(info, None if content is None else io.BytesIO(content))
    return buffer.getvalue()


class RuntimeBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.spec = fetch.runtime_spec("4.2.0")

    def tearDown(self):
        self.temporary.cleanup()

    def test_fixed_official_versions_and_no_arbitrary_url(self):
        self.assertEqual(set(fetch.SUPPORTED_VERSIONS), {"4.2.0", "5.1.2"})
        for version in fetch.SUPPORTED_VERSIONS:
            spec = fetch.runtime_spec(version)
            self.assertTrue(spec["url"].startswith("https://download.blender.org/release/Blender"))
            self.assertRegex(spec["sha256"], r"^[a-f0-9]{64}$")
            self.assertIn(version, spec["filename"])
        with self.assertRaises(ValueError):
            fetch.runtime_spec("../../other")
        with mock.patch.object(fetch.urllib.request, "urlopen") as network:
            with self.assertRaises(RuntimeError):
                fetch._download_verified("http://example.org/blender.tar.xz", self.root / "output", "a" * 64)
            network.assert_not_called()

    def test_verified_download_and_digest_mismatch_cleanup(self):
        payload = b"tiny integrity fixture"
        good = hashlib.sha256(payload).hexdigest()
        destination = self.root / "good.tar.xz"
        with mock.patch.object(
            fetch.urllib.request, "urlopen", return_value=FakeResponse(payload, self.spec["url"], str(len(payload)))
        ):
            fetch._download_verified(self.spec["url"], destination, good)
        self.assertEqual(destination.read_bytes(), payload)
        target = self.root / "bad.tar.xz"
        with mock.patch.object(fetch.urllib.request, "urlopen", return_value=FakeResponse(payload, self.spec["url"])):
            with self.assertRaisesRegex(RuntimeError, "SHA256"):
                fetch._download_verified(self.spec["url"], target, "0" * 64)
        self.assertFalse(target.exists())
        with mock.patch.object(fetch.urllib.request, "urlopen", return_value=FakeResponse(payload, self.spec["url"])):
            with self.assertRaises(FileExistsError):
                fetch._download_verified(self.spec["url"], destination, good)
        self.assertEqual(destination.read_bytes(), payload)

    def test_redirect_and_stream_size_limits(self):
        for final in ("https://example.org/runtime", "http://download.blender.org/release/runtime"):
            with mock.patch.object(fetch.urllib.request, "urlopen", return_value=FakeResponse(b"data", final)):
                with self.assertRaises(RuntimeError):
                    fetch._download_verified(self.spec["url"], self.root / "bad", hashlib.sha256(b"data").hexdigest())
        self.assertFalse((self.root / "bad").exists())
        with mock.patch.object(fetch, "MAX_DOWNLOAD_BYTES", 2):
            for declared in (None, "4", "not a length"):
                with mock.patch.object(
                    fetch.urllib.request, "urlopen", return_value=FakeResponse(b"data", self.spec["url"], declared)
                ):
                    with self.assertRaises(RuntimeError):
                        fetch._download_verified(
                            self.spec["url"], self.root / "oversized", hashlib.sha256(b"data").hexdigest()
                        )
                self.assertFalse((self.root / "oversized").exists())

    def test_safe_internal_links_and_reject_escape_or_device(self):
        name = self.spec["directory"]
        real = tarfile.TarInfo(name + "/lib/real.so")
        real.size = 3
        real.mode = 0o644
        link = tarfile.TarInfo(name + "/lib/alias.so")
        link.type = tarfile.SYMTYPE
        link.linkname = "real.so"
        good = self.root / "links.tar.xz"
        good.write_bytes(runtime_tar(name, [(real, b"lib"), (link, None)]))
        binary = fetch._safe_extract(good, self.root / "valid", name)
        self.assertEqual(binary.read_bytes()[:4], b"\x7fELF")
        self.assertTrue(os.access(binary, os.X_OK))
        self.assertEqual((binary.parent / "lib/alias.so").read_bytes(), b"lib")
        bad_members = []
        for path in (name + "/../../escape", "/absolute", "other-root/file"):
            item = tarfile.TarInfo(path)
            item.size = 1
            bad_members.append((item, b"x"))
        item = tarfile.TarInfo(name + "/escape-link")
        item.type = tarfile.SYMTYPE
        item.linkname = "../../outside"
        bad_members.append((item, None))
        item = tarfile.TarInfo(name + "/escape-hardlink")
        item.type = tarfile.LNKTYPE
        item.linkname = "../outside"
        bad_members.append((item, None))
        item = tarfile.TarInfo(name + "/device")
        item.type = tarfile.CHRTYPE
        bad_members.append((item, None))
        for index, member in enumerate(bad_members):
            path = self.root / f"bad{index}.tar.xz"
            path.write_bytes(runtime_tar(name, [member]))
            with self.subTest(member=member[0].name), self.assertRaises(RuntimeError):
                fetch._safe_extract(path, self.root / f"bad{index}", name)
        self.assertFalse((self.root / "escape").exists())
        self.assertFalse((self.root / "outside").exists())

    def test_unpack_budget_and_duplicate_member_refused(self):
        path = self.root / "runtime.tar.xz"
        path.write_bytes(runtime_tar(self.spec["directory"]))
        with mock.patch.object(fetch, "MAX_UNPACKED_BYTES", 1), self.assertRaises(RuntimeError):
            fetch._safe_extract(path, self.root / "oversized", self.spec["directory"])
        duplicate = tarfile.TarInfo(self.spec["directory"] + "/blender")
        duplicate.size = 1
        path.write_bytes(runtime_tar(self.spec["directory"], [(duplicate, b"x")]))
        with self.assertRaises(RuntimeError):
            fetch._safe_extract(path, self.root / "duplicate", self.spec["directory"])

    def test_full_mocked_fetch_and_existing_directory_protected(self):
        payload = runtime_tar(self.spec["directory"])
        checksum = hashlib.sha256(payload).hexdigest()
        destination = self.root / "installed"
        with (
            mock.patch.object(fetch, "SUPPORTED_VERSIONS", {"4.2.0": checksum}),
            mock.patch.object(fetch.urllib.request, "urlopen", return_value=FakeResponse(payload, self.spec["url"])),
        ):
            binary = fetch.fetch_runtime("4.2.0", destination)
        self.assertTrue(binary.is_file())
        record = json.loads((destination / "VERIFIED_RUNTIME.json").read_text())
        self.assertEqual(record["sha256"], checksum)
        sentinel = destination / "keep"
        sentinel.write_text("existing directory")
        with mock.patch.object(fetch.urllib.request, "urlopen") as network:
            with self.assertRaises(FileExistsError):
                fetch.fetch_runtime("4.2.0", destination)
            network.assert_not_called()
        self.assertEqual(sentinel.read_text(), "existing directory")
        self.assertFalse(list(self.root.glob(".blender-ci-*")))

    def _native_reports(self):
        reports = self.root / "reports"
        for relative in fetch.NATIVE_REPORTS:
            path = reports / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative in fetch.NAMED_REPORT_CHECKS:
                result = {
                    "all_passed": True,
                    "checks": dict.fromkeys(fetch.NAMED_REPORT_CHECKS[relative], True),
                    "blender_version": "4.2.0",
                }
                if relative.startswith("i18n/"):
                    result.pop("all_passed")
                    result["blender"] = result.pop("blender_version")
                    result.update(catalog_entries=400, cached_enum_tables=2, global_preferences_unchanged=True)
                else:
                    result["assets"] = [
                        {
                            "filename": "mixamo_default_" + colour + ".fbx",
                            "sha256": "a" * 64,
                            "bones": 50,
                            "meshes": 2,
                            "vertices": 27850,
                        }
                        for colour in ("white", "black")
                    ]
            elif relative in ("vmd/verification.json", "operators/verification.json"):
                result = {"all_passed": True, "checks": {"test": True}, "blender_version": "4.2.0"}
            else:
                result = {
                    "passed": 1,
                    "total": 1,
                    "checks": [{"id": "test", "passed": True}],
                    "blender_version": "4.2.0",
                }
            if relative == "adversarial/report.json":
                result["source_file_unchanged"] = True
            path.write_text(json.dumps(result))
        return reports

    def test_native_reports_cannot_pass_on_exit_code_alone(self):
        reports = self._native_reports()
        self.assertEqual(fetch.verify_reports(reports, "4.2.0"), list(fetch.NATIVE_REPORTS))
        p = reports / "adversarial/report.json"
        data = json.loads(p.read_text())
        data["checks"][0]["passed"] = False
        p.write_text(json.dumps(data))
        with self.assertRaises(RuntimeError):
            fetch.verify_reports(reports, "4.2.0")
        data["checks"][0]["passed"] = True
        data["source_file_unchanged"] = False
        p.write_text(json.dumps(data))
        with self.assertRaises(RuntimeError):
            fetch.verify_reports(reports, "4.2.0")
        with self.assertRaises(RuntimeError):
            fetch.verify_reports(reports, "5.1.2")
        p.unlink()
        with self.assertRaises(FileNotFoundError):
            fetch.verify_reports(reports, "4.2.0")

    def test_new_native_reports_require_complete_successful_checks(self):
        reports = self._native_reports()
        for relative, required in fetch.NAMED_REPORT_CHECKS.items():
            path = reports / relative
            original = json.loads(path.read_text())
            check = next(iter(required))
            for value in (False, 1, None):
                data = json.loads(json.dumps(original))
                data["checks"][check] = value
                path.write_text(json.dumps(data))
                with self.subTest(report=relative, value=value), self.assertRaises(RuntimeError):
                    fetch.verify_reports(reports, "4.2.0")
            data = json.loads(json.dumps(original))
            del data["checks"][check]
            path.write_text(json.dumps(data))
            with self.subTest(report=relative, missing_check=check), self.assertRaises(RuntimeError):
                fetch.verify_reports(reports, "4.2.0")
            path.write_text(json.dumps(original))
            path.unlink()
            with self.subTest(report=relative, missing_file=True), self.assertRaises(FileNotFoundError):
                fetch.verify_reports(reports, "4.2.0")
            path.write_text(json.dumps(original))

    def test_i18n_gate_requires_global_preferences_and_actual_catalogue(self):
        reports = self._native_reports()
        path = reports / "i18n/i18n_report.json"
        original = json.loads(path.read_text())
        for key, value in [
            ("global_preferences_unchanged", False),
            ("global_preferences_unchanged", 1),
            ("catalog_entries", 0),
            ("catalog_entries", True),
            ("cached_enum_tables", 0),
            ("cached_enum_tables", "2"),
            ("blender", "5.1.2"),
        ]:
            data = {**original, key: value}
            path.write_text(json.dumps(data))
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                fetch.verify_reports(reports, "4.2.0")

    def test_template_gate_requires_two_distinct_native_assets(self):
        reports = self._native_reports()
        path = reports / "templates/verification.json"
        original = json.loads(path.read_text())
        cases = []
        for key, value in [
            ("filename", "mixamo_default_pink.fbx"),
            ("sha256", "not a digest"),
            ("bones", 0),
            ("meshes", True),
            ("vertices", -1),
        ]:
            data = json.loads(json.dumps(original))
            data["assets"][0][key] = value
            cases.append(data)
        cases.extend(
            [
                {**original, "all_passed": False},
                {**original, "assets": []},
                {**original, "assets": [original["assets"][0]] * 2},
            ]
        )
        for index, data in enumerate(cases):
            path.write_text(json.dumps(data))
            with self.subTest(case=index), self.assertRaises(RuntimeError):
                fetch.verify_reports(reports, "4.2.0")

    def test_workflow_pins_versions_and_read_only_permissions(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("ruff==0.14.4", workflow)
        self.assertIn('blender: ["4.2.0", "5.1.2"]', workflow)
        self.assertIn("--verify-reports verification", workflow)
        for script in [
            "test_vmd_roundtrip.py",
            "test_cleanup.py",
            "test_fbx_profiles.py",
            "test_operators.py",
            "test_vmd_adversarial.py",
            "test_install.py",
            "test_retarget.py",
            "test_character_pipeline.py",
            "test_i18n.py",
            "test_templates.py",
        ]:
            self.assertTrue((ROOT / "tests/blender" / script).is_file())
            self.assertIn("tests/blender/" + script, workflow)
        self.assertEqual(workflow.count("--python-exit-code 1"), len(fetch.NATIVE_REPORTS))
        for action in ["softprops/action-gh-release", "actions/create-release", "gh release create"]:
            self.assertNotIn(action, workflow)

    def test_build_cli_accepts_output_outside_repository(self):
        output = self.root / "outside-repository.zip"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_release.py"), "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())
        self.assertIn(str(output), result.stdout)

    def test_windows_workflow_pins_official_archives_and_checks_all_native_groups(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        windows = workflow.split("  blender-windows:", 1)[1].split("  blender-native:", 1)[0]
        self.assertIn("runs-on: windows-2022", windows)
        self.assertIn("shell: pwsh", windows)
        for digest in (
            "b6e72874f8cb5c4ed77f9b03d7f1fde851b9455a7ff02a1e1119c876318ebc65",
            "345bedea7b0acf7cc9666423d8553f9129622aea34ded65c23e8cb70f83f14ff",
        ):
            self.assertIn(digest, windows)
        self.assertIn("https://download.blender.org/release/Blender$series/$filename", windows)
        self.assertLess(windows.index("Get-FileHash"), windows.index("Expand-Archive"))
        self.assertIn("$actual -ne", windows)
        self.assertIn("BLENDER_USER_CONFIG", windows)
        self.assertIn("BLENDER_USER_SCRIPTS", windows)
        self.assertIn('if ($LASTEXITCODE -ne 0)', windows)
        self.assertIn('if ($case.Key -eq "install") { $output }', windows)
        self.assertIn("--verify-reports verification", windows)
        cases = windows.split("$cases = [ordered]@{", 1)[1].split("}", 1)[0]
        for group in fetch.NATIVE_REPORTS:
            self.assertIn(group.split("/", 1)[0] + " = ", cases)
        self.assertEqual(cases.count('"tests/blender/test_'), len(fetch.NATIVE_REPORTS))


if __name__ == "__main__":
    unittest.main()
