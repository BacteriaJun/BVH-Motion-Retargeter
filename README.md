# BVH Motion Retargeter

> **4.0.0 RC1 is an unreleased local candidate.** Priorities: editable VMD, Mixamo FBX, and UE4/UE5 FBX. The release badge below still refers to the published version.

## Editable VMD workflow

Select **VMD** in the sidebar, import to the generic **Reference Preview** or a compatible selected MMD rig, edit the Action or create a bounded denoised copy, then **Preserve Imported VMD** on export. Untouched files retain their original bytes. Edited mapped bones are resampled at 30 Hz; original morph, camera, light, shadow, IK-switch and unmapped tracks are retained.

VMD has no rest skeleton. Reference geometry is for FK/control-channel review; native MMD IK, append transforms, model morphs and physics require the appropriate model environment. Name aliases resolve full-width/ASCII digits without renaming original VMD records; ambiguous bindings are rejected.

Explicit **New FK Motion** export also accepts mapped BVH/Mixamo motion. Match target MMD rest axes and units; new FK files explicitly disable standard leg/toe IK. Source-preserving export keeps the original IK switches and time origin.

[Detailed VMD workflow](docs/vmd-workflow.md) · [Root-motion validation](docs/root-motion-validation.md) · [Release readiness](docs/release-readiness.md)

## Cleanup and output checks

- Bounded SO(3) cleanup creates a separate object/Action; root travel, fingers and IK control rotations are excluded by default. Selected-bone editing is available.
- Short root repair requires source-video confirmation and trusted samples on both sides; terminal corruption is diagnosed rather than guessed.
- Mixamo and generic UE4/UE5 FBX profiles use explicit axes and per-frame sampling without exporter key reduction. Retarget to the actual engine Skeleton.
- New Unreal root bones start at model origin. Horizontal root allocation uses world XY while preserving body motion and height; existing root rest geometry is retained.
- Export preflight checks discontinuities/nonfinite animation, protects existing output files and restores selection/frame/subframe. Package builds reject private captures and unreviewed modules.


> Retarget BVH motion to Mixamo, Unreal Engine 5, and VRM humanoid rigs directly in Blender.

[![Release](https://img.shields.io/github/v/release/BacteriaJun/BVH-Motion-Retargeter)](https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/latest)
[![CI](https://github.com/BacteriaJun/BVH-Motion-Retargeter/actions/workflows/ci.yml/badge.svg)](https://github.com/BacteriaJun/BVH-Motion-Retargeter/actions/workflows/ci.yml)
[![Blender](https://img.shields.io/badge/Blender-4.2%2B-orange)](https://www.blender.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**English** | [简体中文](README_zh-CN.md)

**BVH Motion Retargeter** is a Blender add-on for converting and retargeting BVH motion-capture data to common humanoid skeleton conventions.

It provides a repeatable workflow for source mapping, constraint-based retargeting, animation baking, motion cleanup, and FBX export.

Supported target workflows include:

* **Mixamo**
* **Unreal Engine 5**
* **VRM humanoid avatars**

---

## Demo

<!--
Add a short demo GIF here after creating docs/assets/demo.gif.

<p align="center">
  <img src="docs/assets/demo.gif" width="900" alt="BVH Motion Retargeter demo">
</p>

<p align="center">
  BVH → Retarget → Bake → Export
</p>
-->

```text
BVH Motion
    │
    ▼
Source Mapping
    │
    ▼
Target Rig Profile
 ┌──────┼──────┐
 ▼      ▼      ▼
Mixamo  UE5    VRM
    │
    ▼
Retarget & Bake
    │
    ▼
Blender Animation / FBX
```

---

## Why BVH Motion Retargeter?

BVH files from different motion-capture systems often use different bone names, hierarchies, frame rates, and coordinate conventions.

Manually adapting these files for character animation can involve repeated renaming, constraint setup, baking, cleanup, and export configuration.

BVH Motion Retargeter brings those steps into a single Blender workflow:

**Import → Map → Retarget → Bake → Export**

---

## Features

### Constraint-Bake Retargeting

Transfers BVH motion to the target armature using Blender constraints and NLA baking, producing real animation keyframes on the destination rig.

### Multiple Target Rig Profiles

Built-in workflows for:

* Mixamo Standard
* Unreal Engine 5 Humanoid
* VRM Humanoid Body

### Flexible Binding

Retarget motion to:

* a generated target armature;
* an existing compatible armature in the scene;
* a built-in character template;
* a custom FBX, VRM, GLB, or GLTF character.

### JSON-Based Source Mapping

Use built-in or custom JSON mappings to adapt BVH files from different motion-capture pipelines without changing the add-on source code.

### Production-Oriented Export

Integrated FBX export presets are available for:

* Mixamo workflows;
* Unreal Engine 5 workflows;
* automatic profile-based export.

### Motion Cleanup Tools

Includes utilities for:

* automatic BVH frame-rate matching;
* optional F-curve simplification;
* root-motion handling;
* VRM thigh-axis correction;
* independent left/right knee compensation.

---

## Supported Targets

| Target              | Skeleton Convention                | Typical Use                                      |
| ------------------- | ---------------------------------- | ------------------------------------------------ |
| **Mixamo**          | `mixamorig:*`                      | Mixamo characters and general humanoid workflows |
| **Unreal Engine 5** | `root`, `pelvis`, `spine_01`, etc. | UE5 humanoid and IK Retargeter workflows         |
| **VRM**             | `J_Bip_*`                          | VRM humanoid avatars                             |

The VRM workflow focuses on humanoid body bones and intentionally ignores secondary physics/accessory bones such as `J_Sec_*` hair, skirt, sleeve, and decoration bones.

---

## Quick Start

### Requirements

* Blender **4.2 or later**
* A `.bvh` motion-capture file

For VRM workflows, a compatible VRM importer may be required to import the model into Blender before retargeting.

### Installation

1. Download the latest release ZIP from **[GitHub Releases](https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/latest)**.
2. In Blender, open **Edit → Preferences → Add-ons** or **Extensions**.
3. Choose **Install from Disk** and select the release ZIP.
4. Enable **BVH Motion Retargeter**.

The add-on panel is located at:

```text
3D Viewport → N Sidebar → BVH Retarget
```

---

## Basic Workflow

### 1. Select Source Motion

Choose the source `.bvh` file.

The add-on can read the BVH frame time and synchronize the Blender scene FPS when requested.

### 2. Select Source Mapping

Use the default mapping or provide a custom JSON mapping for the source skeleton.

### 3. Choose Target Profile

Select:

```text
Mixamo Standard
Unreal Engine 5 Humanoid
VRM Humanoid Body
```

### 4. Choose Binding Mode

Select one of:

```text
Create Target Armature
Bind to Selected Armature
Bind to Character Template
```

### 5. Retarget and Bake

Configure the retargeting settings and bake the transferred animation to the target skeleton.

### 6. Export

Export the result using the integrated Mixamo, UE5, or automatic FBX preset.

---

## Character Templates

BVH Motion Retargeter includes several Mixamo-compatible character template variants:

* Default
* White
* Pink
* Purple
* Black
* Green

Templates are stored outside the main source history and fetched using checksum-verified release assets when preparing the repository or building a release package.

---

## Custom Source Mapping

Bone mappings are stored as JSON files.

This allows motion from different BVH skeleton conventions to be adapted without modifying the retargeting implementation.

Example concept:

```json
{
  "Hips": "mixamorig:Hips",
  "Spine": "mixamorig:Spine",
  "LeftArm": "mixamorig:LeftArm",
  "RightArm": "mixamorig:RightArm"
}
```

Additional mappings can be added under:

```text
bvh_to_mixamo/presets/
```

---

## Project Structure

```text
BVH-Motion-Retargeter/
├── bvh_to_mixamo/
│   ├── core/
│   ├── operators/
│   ├── presets/
│   ├── templates/
│   └── ui/
│
├── docs/
├── scripts/
├── tests/
│
├── .github/workflows/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── README_zh-CN.md
└── pyproject.toml
```

The repository separates Blender runtime code from documentation, tests, release tooling, and CI configuration.

---

## Development

Clone the repository:

```bash
git clone https://github.com/BacteriaJun/BVH-Motion-Retargeter.git
cd BVH-Motion-Retargeter
```

Install the lint tool:

```bash
python -m pip install ruff
```

Fetch verified character templates:

```bash
python scripts/fetch_templates.py
```

Run repository checks:

```bash
ruff check .
python -m compileall -q bvh_to_mixamo scripts tests
python -m unittest discover -s tests -v
```

Build an installable Blender package:

```bash
python scripts/build_release.py
```

The generated release ZIP is written to:

```text
dist/
```

---

## Continuous Integration

GitHub Actions validates the repository on pushes and pull requests.

The current CI pipeline performs:

* Ruff linting;
* Python bytecode compilation;
* checksum-verified template retrieval;
* repository unit tests;
* release package generation.

---

## Documentation

Additional documentation is available in [`docs/`](docs/).

Current resources:

* [User Guide](docs/user-guide.md)
* [Changelog](CHANGELOG.md)
* [Contributing Guide](CONTRIBUTING.md)

More detailed documentation for target skeletons, custom mappings, architecture, and troubleshooting can be maintained separately from the main README as the project grows.

---

## Contributing

Contributions, bug reports, and improvements are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

For behavior-related changes, include the Blender version used for testing and keep pull requests focused on a specific improvement.

---

## Releases

Stable installable packages are published through:

**[GitHub Releases](https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/latest)**

Generated release ZIP files are not stored directly on the main source branch.

---

## Author

**Junius Tang / BacteriaJun**

GitHub: [@BacteriaJun](https://github.com/BacteriaJun)

---

## License

This project is licensed under the [MIT License](LICENSE).
