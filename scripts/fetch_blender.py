#!/usr/bin/env python3
"""Fetch pinned official Linux CI runtimes, or verify native JSON reports.

This development helper is not distributed inside the installable Blender add-on.
Official SHA256 files checked 2026-11-04:
https://download.blender.org/release/Blender4.2/blender-4.2.0.sha256
https://download.blender.org/release/Blender5.1/blender-5.1.2.sha256
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

SUPPORTED_VERSIONS = {
    "4.2.0": "4f4fd7646af01f6fee9d420408318381a6e52571268eb7cf9cd5033bd9e7a359",
    "5.1.2": "aaccb355f50183979b698bcce7467103a76261b5fa59f4972295842662a285fb",
}
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
MAX_UNPACKED_BYTES = 6 * 1024 * 1024 * 1024
MAX_MEMBERS = 100_000
NATIVE_REPORTS = (
    "vmd/verification.json",
    "cleanup/cleanup_verification.json",
    "fbx/fbx_verification.json",
    "operators/verification.json",
    "adversarial/report.json",
    "install/verification.json",
    "retarget/verification.json",
    "character/verification.json",
)


def runtime_spec(version):
    if not isinstance(version, str) or version not in SUPPORTED_VERSIONS:
        raise ValueError("Supported CI Blender versions: " + ", ".join(SUPPORTED_VERSIONS))
    series = ".".join(version.split(".")[:2])
    filename = f"blender-{version}-linux-x64.tar.xz"
    return {
        "version": version,
        "filename": filename,
        "directory": filename.removesuffix(".tar.xz"),
        "url": f"https://download.blender.org/release/Blender{series}/{filename}",
        "sha256": SUPPORTED_VERSIONS[version],
    }


def _official_https(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "download.blender.org" or not parsed.path.startswith("/release/"):
        raise RuntimeError("Runtime downloads must remain on Blender official HTTPS release URLs")


def _download_verified(url, target, expected_hash):
    _official_https(url)
    target = Path(target)
    created = False
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            _official_https(response.geturl())  # Reject insecure or off-host redirects.
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isdecimal() or int(declared) > MAX_DOWNLOAD_BYTES):
                raise RuntimeError("Runtime download has an invalid or oversized Content-Length")
            digest = hashlib.sha256()
            total = 0
            with target.open("xb") as output:
                created = True
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError("Runtime download exceeded the size budget")
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != expected_hash:
                raise RuntimeError("Official Blender runtime SHA256 mismatch")
            if declared is not None and total != int(declared):
                raise RuntimeError("Runtime download length mismatch")
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def _safe_extract(archive_path, directory, expected_root):
    """Validate names, links, types and resource bounds before extracting."""
    directory = Path(directory)
    if (
        not isinstance(expected_root, str)
        or len(PurePosixPath(expected_root).parts) != 1
        or expected_root in {".", ".."}
        or "\\" in expected_root
    ):
        raise ValueError("Expected runtime root must be one directory name")
    directory.mkdir(parents=True, exist_ok=True)
    root = directory.resolve() / expected_root
    with tarfile.open(archive_path, mode="r:xz") as archive:
        members = []
        total = 0
        seen = set()
        for member in archive:
            relative = PurePosixPath(member.name)
            if (
                relative.is_absolute()
                or not relative.parts
                or relative.parts[0] != expected_root
                or ".." in relative.parts
                or "\\" in member.name
            ):
                raise RuntimeError("Runtime archive contains an unsafe member path")
            canonical = relative.as_posix()
            if canonical in seen:
                raise RuntimeError("Runtime archive contains duplicate member paths")
            seen.add(canonical)
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise RuntimeError("Runtime archive contains a device or unsupported member type")
            if member.size < 0:
                raise RuntimeError("Runtime archive contains a negative member size")
            total += member.size
            if total > MAX_UNPACKED_BYTES or len(members) >= MAX_MEMBERS:
                raise RuntimeError("Runtime archive exceeded the extraction budget")
            if member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or "\\" in member.linkname:
                    raise RuntimeError("Runtime archive contains an unsafe link")
                base = directory / relative.parent if member.issym() else directory
                target = (base / Path(*link.parts)).resolve()
                if not target.is_relative_to(root):
                    raise RuntimeError("Runtime archive link escapes its own root")
            members.append(member)
        # Python's data filter additionally checks actual symlink resolution as
        # members are extracted, including chains not present during preflight.
        archive.extractall(directory, members=members, filter="data")
    binary = root / "blender"
    if binary.is_symlink() or not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("Verified archive has no executable Blender binary")
    with binary.open("rb") as source:
        if source.read(4) != b"\x7fELF":
            raise RuntimeError("Expected the official Linux ELF Blender binary")
    return binary


def fetch_runtime(version, destination):
    """Create a fresh runtime directory; never delete or overwrite an old one."""
    spec = runtime_spec(version)
    destination = Path(destination).expanduser()
    if any(ch in str(destination) for ch in ("\r", "\n", "\x00")):
        raise ValueError("Runtime destination must not contain control separators")
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Use a fresh CI runtime destination; existing directories are preserved")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".blender-ci-", dir=destination.parent) as scratch:
        scratch = Path(scratch)
        archive = scratch / spec["filename"]
        _download_verified(spec["url"], archive, spec["sha256"])
        unpacked = scratch / "unpacked"
        binary = _safe_extract(archive, unpacked, spec["directory"])
        record = {
            **spec,
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "scope": "Verified official Linux archive, not a claim that native tests have run.",
        }
        (unpacked / "VERIFIED_RUNTIME.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        # copytree's exclusive destination creation also prevents overwriting a
        # directory created by another process since our initial preflight.
        shutil.copytree(unpacked, destination, symlinks=True)
    return destination / spec["directory"] / "blender"


def _reject_json_constant(value):
    raise ValueError("Nonfinite JSON constant in a native test report: " + value)


def verify_reports(directory, expected_version=None):
    """A process exiting zero is insufficient when a test collects failures."""
    if expected_version is not None:
        runtime_spec(expected_version)
    directory = Path(directory)
    validated = []
    for relative in NATIVE_REPORTS:
        path = directory / relative
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
        if not isinstance(data, dict):
            raise RuntimeError("Native report must be a JSON object: " + relative)
        version = data.get("blender_version", data.get("blender", ""))
        if expected_version and (
            not isinstance(version, str) or not version.split() or version.split()[0] != expected_version
        ):
            raise RuntimeError("Native report came from an unexpected Blender runtime: " + relative)
        checks = data.get("checks")
        if "all_passed" in data:
            if (
                data["all_passed"] is not True
                or not isinstance(checks, dict)
                or not checks
                or not all(v is True for v in checks.values())
            ):
                raise RuntimeError("Native checks did not all pass: " + relative)
        else:
            passed, total = data.get("passed"), data.get("total")
            if (
                type(passed) is not int
                or type(total) is not int
                or total <= 0
                or passed != total
                or not isinstance(checks, list)
                or len(checks) != total
                or any(not isinstance(c, dict) or c.get("passed") is not True for c in checks)
            ):
                raise RuntimeError("Collected native failures or missing checks: " + relative)
        if relative == "adversarial/report.json" and data.get("source_file_unchanged") is not True:
            raise RuntimeError("The adversarial source was modified")
        validated.append(relative)
    return validated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=tuple(SUPPORTED_VERSIONS))
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--verify-reports", type=Path)
    parser.add_argument("--expected-version", choices=tuple(SUPPORTED_VERSIONS))
    args = parser.parse_args()
    if args.verify_reports:
        if args.version or args.destination or args.github_output:
            parser.error("Report verification is separate from runtime downloading")
        verified = verify_reports(args.verify_reports, args.expected_version)
        print("Validated native reports: " + ", ".join(verified))
        return
    if not args.version or args.destination is None or args.expected_version:
        parser.error("Downloading needs --version and --destination")
    binary = fetch_runtime(args.version, args.destination)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"blender_path={binary}\n")
    print(f"Verified Blender runtime: {binary}")


if __name__ == "__main__":
    main()
