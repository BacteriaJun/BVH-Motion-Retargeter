#!/usr/bin/env python3
"""Build a deterministic, validated Blender install ZIP without private captures."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import tempfile
import tomllib
import zipfile
from pathlib import Path

try:
    from fetch_templates import TEMPLATE_SHA256
except ModuleNotFoundError:
    from scripts.fetch_templates import TEMPLATE_SHA256

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "bvh_to_mixamo"
MANIFEST = PACKAGE / "blender_manifest.toml"
ADDON_INFO = PACKAGE / "addon_info.py"
EXCLUDED_PARTS = {"__pycache__", "docs", "tests"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
REQUIRED_TEMPLATES = frozenset(TEMPLATE_SHA256)
# Explicit source manifest: a newly added product module must be reviewed here.
# Merely having a .py suffix does not authorize packaging an external reference.
CODE_FILES = frozenset(
    {
        "__init__.py",
        "addon_info.py",
        "properties.py",
        "core/__init__.py",
        "core/animation_utils.py",
        "core/i18n.py",
        "core/i18n_errors.py",
        "core/armature_utils.py",
        "core/bone_data.py",
        "core/bone_mapping.py",
        "core/bvh_parser.py",
        "core/export_profiles.py",
        "core/logger.py",
        "core/mmd_mapping.py",
        "core/motion_cleanup.py",
        "core/motion_math.py",
        "core/paths.py",
        "core/retarget_engine.py",
        "core/template_loader.py",
        "core/ue5_profile.py",
        "core/vmd_blender.py",
        "core/vmd_codec.py",
        "core/vrm_profile.py",
        "operators/__init__.py",
        "operators/convert.py",
        "operators/export_fbx.py",
        "operators/file_selectors.py",
        "operators/import_bvh.py",
        "operators/retarget.py",
        "operators/template.py",
        "operators/vmd_io.py",
        "operators/motion_cleanup.py",
        "ui/__init__.py",
        "ui/panel.py",
    }
)
OPTIONAL_CODE_FILES = frozenset()
VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
PRESET_STEM = re.compile(r"[a-z][a-z0-9_]*\Z")


def _version(value):
    if not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value):
        raise RuntimeError("Release version must be a safe major.minor.patch string")
    return value


def manifest_version(text: str | None = None) -> str:
    try:
        data = tomllib.loads(MANIFEST.read_text(encoding="utf-8") if text is None else text)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError("Invalid Blender extension manifest") from exc
    if data.get("id") != "bvh_to_mixamo" or data.get("type") != "add-on":
        raise RuntimeError("Unexpected Blender extension id or package type")
    if data.get("license") != ["SPDX:MIT"]:
        raise RuntimeError("Extension license must match the repository MIT license")
    return _version(data.get("version"))


def addon_version(text: str | None = None) -> str:
    tree = ast.parse(ADDON_INFO.read_text(encoding="utf-8") if text is None else text, filename=str(ADDON_INFO))
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ADDON_VERSION" for target in node.targets
        ):
            values.append(ast.literal_eval(node.value))
    if len(values) != 1:
        raise RuntimeError("Exactly one ADDON_VERSION assignment is required")
    value = values[0]
    if not isinstance(value, tuple) or len(value) != 3 or any(type(v) is not int or v < 0 for v in value):
        raise RuntimeError("ADDON_VERSION must be three nonnegative integer components")
    return _version(".".join(str(part) for part in value))


def validate_discovery_metadata(entrypoint: str, manifest: str, version: str) -> None:
    """Blender discovers legacy ZIP add-ons from a literal bl_info dictionary."""
    assignments = [
        node.value
        for node in ast.parse(entrypoint).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets)
    ]
    try:
        info = ast.literal_eval(assignments[0]) if len(assignments) == 1 else None
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Blender discovery requires literal bl_info metadata") from exc
    data = tomllib.loads(manifest)
    if not isinstance(info, dict) or (
        info.get("version") != tuple(int(part) for part in version.split("."))
        or info.get("blender") != tuple(int(part) for part in data["blender_version_min"].split("."))
        or info.get("name") != data["name"]
    ):
        raise RuntimeError("Blender discovery bl_info metadata must match the manifest and add-on version")


def _allowed(relative):
    name = relative.as_posix()
    if name in CODE_FILES | OPTIONAL_CODE_FILES or name == "blender_manifest.toml" or name == "templates/README.md":
        return True
    if len(relative.parts) == 2 and relative.parts[0] == "presets" and relative.suffix == ".json":
        return bool(PRESET_STEM.fullmatch(relative.stem))
    return name in {"templates/" + item for item in REQUIRED_TEMPLATES}


def package_files() -> list[Path]:
    """Reject unexpected content instead of silently including a customer asset."""
    if PACKAGE.is_symlink() or not PACKAGE.is_dir():
        raise RuntimeError("Package must be a local, nonsymlink directory")
    files = []
    unexpected = []
    for path in sorted(PACKAGE.rglob("*")):
        relative = path.relative_to(PACKAGE)
        if path.is_symlink():
            raise RuntimeError(f"Package symlinks are not permitted: {relative}")
        if not path.is_file():
            continue
        if EXCLUDED_PARTS.intersection(relative.parts) or path.suffix in EXCLUDED_SUFFIXES or path.name == ".DS_Store":
            continue
        if not _allowed(relative):
            unexpected.append(relative.as_posix())
        else:
            files.append(path)
    if unexpected:
        raise RuntimeError(
            "Unexpected package files; move private captures/references outside the add-on: "
            + ", ".join(unexpected[:20])
        )
    missing = sorted(CODE_FILES - {p.relative_to(PACKAGE).as_posix() for p in files})
    if missing:
        raise RuntimeError("Missing required product modules: " + ", ".join(missing))
    return files


def _no_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _validate_preset(payload, name):
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_no_duplicate_json_keys)
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError(f"Invalid mapping preset JSON: {name}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Mapping preset must be an object: {name}")
    if "mapping" in data:
        extra = set(data) - {"name", "description", "version", "target", "profile", "mapping"}
        if extra or any(not isinstance(v, str) for k, v in data.items() if k != "mapping"):
            raise RuntimeError(f"Unexpected preset metadata: {name}")
        mapping = data["mapping"]
    else:
        mapping = data
    if (
        not isinstance(mapping, dict)
        or not mapping
        or not all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in mapping.items())
    ):
        raise RuntimeError(f"Preset requires a nonempty string-to-string bone mapping: {name}")


def _license_bytes():
    paths = [p for p in (ROOT / "LICENSE", ROOT / "LICENSE.txt") if p.is_file()]
    if not paths or any(p.is_symlink() for p in paths):
        raise RuntimeError("A local repository MIT LICENSE or LICENSE.txt is required")
    values = [p.read_bytes() for p in paths]
    if any(value != values[0] for value in values):
        raise RuntimeError("Repository license files disagree")
    text = values[0].decode("utf-8")
    if (
        "MIT License" not in text
        or "Copyright" not in text
        or "Permission is hereby granted, free of charge" not in text
    ):
        raise RuntimeError("Repository license is not the expected MIT attribution")
    return values[0]


def build(output: Path) -> Path:
    output = Path(output).expanduser()
    if output.is_symlink():
        raise RuntimeError("The output archive must not be a symlink")
    output = output.resolve()
    if output.suffix.lower() != ".zip" or output.is_relative_to(PACKAGE.resolve()):
        raise RuntimeError("Output must be a .zip file outside the installable package")
    # Snapshot all payload bytes before validation/build, avoiding mixed reads.
    payloads = {p.relative_to(PACKAGE).as_posix(): p.read_bytes() for p in package_files()}
    version = manifest_version(payloads["blender_manifest.toml"].decode("utf-8"))
    code_version = addon_version(payloads["addon_info.py"].decode("utf-8"))
    if version != code_version:
        raise RuntimeError(f"Version mismatch: manifest={version}, addon_info={code_version}")
    validate_discovery_metadata(
        payloads["__init__.py"].decode("utf-8"), payloads["blender_manifest.toml"].decode("utf-8"), version
    )
    missing_templates = REQUIRED_TEMPLATES - {Path(name).name for name in payloads if name.startswith("templates/")}
    if missing_templates:
        raise RuntimeError(
            "Missing bundled templates. Run python scripts/fetch_templates.py first: "
            + ", ".join(sorted(missing_templates))
        )
    for name, expected in TEMPLATE_SHA256.items():
        actual = hashlib.sha256(payloads["templates/" + name]).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Bundled template checksum mismatch: {name}")
    for name, payload in payloads.items():
        if name.endswith(".py"):
            compile(payload, name, "exec")
        elif name.startswith("presets/"):
            _validate_preset(payload, name)
    payloads["LICENSE.txt"] = _license_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".bvh-release-", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, payload in sorted(payloads.items()):
                info = zipfile.ZipInfo("bvh_to_mixamo/" + relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Archive verification failed")
        os.replace(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return output


def main() -> None:
    version = manifest_version()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / f"bvh_motion_retargeter_v{version}_release.zip",
        help="Output ZIP path",
    )
    args = parser.parse_args()
    output = build(args.output)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
