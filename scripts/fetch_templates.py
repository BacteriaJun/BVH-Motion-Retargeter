#!/usr/bin/env python3
"""Prepare the two bundled Mixamo templates from the pinned release resource."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "bvh_to_mixamo" / "templates"
RELEASE_URL = (
    "https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/download/"
    "V3.2.0/bvh_motion_retargeter_v3.2.0_release.zip"
)
ARCHIVE_SHA256 = "8c137abbef58f59f70c7b3c7900d368c68b252d1284512310c57f5d1e93aacbb"
TEMPLATE_SHA256 = {
    "mixamo_default_black.fbx": "dab537495fa0319d5726ccc8e7ea5b19202aee77cdf604b1d635e5d6404f8dc3",
    "mixamo_default_white.fbx": "ae11767e5b5940ae6e7a900667cc1148e44c7cfce3bccdcdf993a6a82efa9ad2",
}
# Remove only exact copies of the four retired bundled resources. A locally
# modified file with one of these names is left for the owner to move or rename.
RETIRED_TEMPLATE_SHA256 = {
    "mixamo_default_character.fbx": "f462c82fc2b114948170930d453696813fa9475d892b1fa75b773bec32f9656f",
    "mixamo_default_green.fbx": "24d848a9ae7e439a7bfff56bfe0c9e9a4f80816df804455381cb72183a48e6b4",
    "mixamo_default_pink.fbx": "f0f34dc825dfd8b6cd3549afc9c8e83e9c7148c36501cb57484141d0d7250ed7",
    "mixamo_default_purple.fbx": "7f8627706a1446eb16e9e08868be144d3f9a0dd484930908f4311f63f850a2aa",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Expected a local template file: {path.name}")
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"Checksum mismatch for {path.name}: expected {expected}, got {actual}")


def retire_duplicate_templates() -> None:
    for name, expected in RETIRED_TEMPLATE_SHA256.items():
        path = OUTPUT_DIR / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or sha256(path) != expected:
            raise RuntimeError(f"Retired template has local changes; move or rename it first: {name}")
        path.unlink()
        print(f"Removed retired template: {name}")


def main() -> None:
    if OUTPUT_DIR.is_symlink():
        raise RuntimeError("Template output directory must be local")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if all(
        (OUTPUT_DIR / name).is_file() and not (OUTPUT_DIR / name).is_symlink() and sha256(OUTPUT_DIR / name) == expected
        for name, expected in TEMPLATE_SHA256.items()
    ):
        retire_duplicate_templates()
        print("Verified existing black and white templates")
        return
    # Verify each staged asset before replacing any existing template.
    with tempfile.TemporaryDirectory(prefix="bvh-retargeter-") as temporary_dir:
        archive_path = Path(temporary_dir) / "release.zip"
        print(f"Downloading {RELEASE_URL}")
        with urllib.request.urlopen(RELEASE_URL) as response, archive_path.open("wb") as output:
            shutil.copyfileobj(response, output)
        verify(archive_path, ARCHIVE_SHA256)
        staged = []
        with zipfile.ZipFile(archive_path) as archive:
            for filename, expected in TEMPLATE_SHA256.items():
                member = f"bvh_to_mixamo/templates/{filename}"
                candidate = Path(temporary_dir) / filename
                with archive.open(member) as source, candidate.open("wb") as output:
                    shutil.copyfileobj(source, output)
                verify(candidate, expected)
                staged.append((candidate, OUTPUT_DIR / filename))
        for candidate, destination in staged:
            fd, temporary = tempfile.mkstemp(prefix=".bvh-template-", suffix=".fbx", dir=OUTPUT_DIR)
            os.close(fd)
            try:
                shutil.copyfile(candidate, temporary)
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            print(f"Verified {destination.relative_to(ROOT)}")
        retire_duplicate_templates()


if __name__ == "__main__":
    main()
