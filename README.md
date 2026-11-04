# BVH Motion Retargeter

[![Release](https://img.shields.io/github/v/release/BacteriaJun/BVH-Motion-Retargeter)](https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/latest)
[![CI](https://github.com/BacteriaJun/BVH-Motion-Retargeter/actions/workflows/ci.yml/badge.svg)](https://github.com/BacteriaJun/BVH-Motion-Retargeter/actions/workflows/ci.yml)
[![Blender](https://img.shields.io/badge/Blender-4.2%2B-orange)](https://www.blender.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**English** | [简体中文](README_zh-CN.md)

**BVH Motion Retargeter 4.0.0** is a Blender add-on for editable VMD motion, BVH retargeting, motion cleanup and Mixamo/UE4/UE5 FBX export.

## What's new in 4.0.0

- **Editable VMD:** import bone and control tracks into Blender, refine the Action, and export while retaining untouched bone, morph, camera, light, shadow and IK-switch records.
- **New FK VMD export:** export mapped BVH/Mixamo motion at the VMD 30 Hz timebase, with explicit standard leg/toe IK switches.
- **Motion cleanup:** create bounded rotation-denoising copies and video-confirmed short root-repair copies while retaining the original object and Action.
- **FBX and root motion:** Mixamo, UE4 and UE5 export profiles; world-axis horizontal root allocation preserves sampled body motion and height.
- **Chinese/English interface:** choose Auto, 简体中文 or English inside the add-on.
- **Two built-in characters:** Black and White Mixamo-compatible templates, plus custom FBX/VRM/GLB/GLTF characters.

## Install and choose a language

Requirements: **Blender 4.2 or later**. Native regression tests have run on macOS arm64 with Blender **4.2.0** and **5.1.2**.

1. Download the installation ZIP from [GitHub Releases](https://github.com/BacteriaJun/BVH-Motion-Retargeter/releases/latest).
2. In Blender, open **Edit → Preferences → Add-ons / Extensions → Install from Disk**.
3. Select the ZIP and enable **BVH Motion Retargeter**.
4. Open **3D Viewport → N Sidebar → BVH Retarget**.
5. At the top of the panel, set **Language / 界面语言** to **Auto**, **简体中文** or **English**. Auto follows Blender's interface language. This setting changes the add-on's interface.

## Refine an existing VMD

1. Select **VMD** and choose the source file.
2. Choose **Reference Preview / 参考骨架预览** to create a reference armature, or **Selected MMD Rig / 所选 MMD 骨架** to use a compatible model rig.
3. Click **Import Editable VMD / 导入可编辑 VMD**.
4. Edit bone/control animation in Blender, or use **Create Denoised Copy / 创建去抖副本**. Save the `.blend` to retain the original VMD and edit session.
5. Select **Preserve Imported VMD / 保留原 VMD 数据** and export to a new file.

Untouched export is byte-identical to the imported VMD. Edited mapped tracks are sampled at 30 Hz; untouched tracks and other VMD sections retain their original records. Finger names with full-width and ASCII digits are matched while retaining the source names.

The reference armature provides FK/control-track editing. The original IK-switch fields are retained. Model-specific IK, append transforms, facial deformation and physics are presented by the corresponding MMD/PMX model environment.

For a new motion from another rig, choose **New FK Motion / 新建 FK 动作**, match the target MMD bone names, rest axes and units, then export. New FK files disable the standard leg/toe IK controls by default.

See [VMD editing and export](docs/vmd-workflow.md) for mappings, sampling and export requirements.

## Retarget BVH and export FBX

1. Choose a `.bvh` file and a built-in or custom JSON source mapping.
2. Choose **Mixamo Standard**, **Unreal Engine 4 Humanoid**, **Unreal Engine 5 Humanoid** or **VRM Humanoid Body**.
3. Create a target armature, bind an existing compatible armature, or choose a character template.
4. Run retarget and bake. The result is an editable Action on the destination rig.
5. Export using **Mixamo FBX**, **UE4 FBX**, **UE5 FBX** or **Auto**.

The add-on can match the scene frame rate to the source BVH. FBX profiles sample each frame with exporter key reduction disabled. Unreal output uses a generic humanoid hierarchy and root bone; use the target Skeleton and retarget settings in the engine project. VRM retargeting uses body bones and leaves `J_Sec_*` accessory/physics bones outside the body mapping.

## Cleanup and root motion

- **Create Denoised Copy** applies bounded SO(3) rotation filtering to a separate object/Action. Root translation, fingers and IK-control rotations are excluded by default. Selected pose bones can be processed separately.
- **Inspect Export Range** locates large root discontinuities and invalid animation data in the chosen range.
- **Create Root Repair Copy** bridges a video-confirmed anomaly of at most 150 ms with trusted samples on both sides. A damaged end segment needs a reviewed export range.
- New Unreal root bones start at the model origin. Root allocation uses world X/Y travel and retains body height and sampled body trajectories. Existing root rest geometry is retained.
- Existing output files require an explicit overwrite choice.

See [root-motion and FBX validation](docs/root-motion-validation.md).

## Character templates

The installation ZIP includes **Black** and **White** Mixamo-compatible characters. **Custom** loads your own FBX, VRM, GLB or GLTF model. Previous Default, Pink, Purple and Green selections migrate to White.

Source checkouts retrieve these two models with SHA256 verification:

```sh
python scripts/fetch_templates.py
```

## Develop and build

```sh
git clone https://github.com/BacteriaJun/BVH-Motion-Retargeter.git
cd BVH-Motion-Retargeter
python -m pip install ruff==0.14.4
python scripts/fetch_templates.py
ruff check .
python -m compileall -q bvh_to_mixamo scripts tests
python -m unittest discover -s tests -v
python scripts/build_release.py
```

The installation ZIP is written to `dist/`. Runtime code lives in `bvh_to_mixamo/`; `docs/`, `tests/`, `scripts/` and CI are maintained separately. Builds verify both template hashes, the package file list and the matching version metadata, and produce deterministic ZIP bytes.

The CI configuration runs repository checks and native Blender 4.2.0/5.1.2 regressions, including VMD, cleanup, FBX, retargeting, character binding, operators, language switching, template migration and isolated installation.

## Documentation

- [User guide](docs/user-guide.md)
- [VMD editing and export](docs/vmd-workflow.md)
- [VMD format and interpolation](docs/vmd-format-notes.md)
- [Root-motion and FBX validation](docs/root-motion-validation.md)
- [Release checks and reproduction commands](docs/release-readiness.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

**Author:** Junius Tang / [BacteriaJun](https://github.com/BacteriaJun)

**License:** [MIT](LICENSE)
