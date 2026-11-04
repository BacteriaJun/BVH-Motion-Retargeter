# Changelog

## 4.0.0

- Added an add-on language selector: Auto, 简体中文 and English.
- Reduced built-in character templates to Black and White; retained custom-model loading and migrated discontinued colour selections to White.
- Added editable VMD import, embedded source-session data, reference FK/control rigs and source-preserving export across all VMD sections.
- Added new FK VMD export with target-name mapping, 30 Hz resampling and standard leg/toe IK-disable flags.
- Added full-width/ASCII finger-name matching while retaining original VMD names; ambiguous bindings produce an explicit error.
- Added bounded SO(3) denoising copies, video-confirmed short root repair and scale-aware export diagnostics.
- Added the UE4 FBX profile and corrected Unreal horizontal root allocation in world axes, preserving body motion and starting new roots at the model origin.
- Fixed Action access across Blender 4.2 and 5.x, export-object selection, frame/subframe restoration and unsupported-edit detection.
- Added bounded simplification for linear baked curves; retained nonlinear curves and original takes.
- Corrected short-BVH export ranges and frame-rate conversion to preserve elapsed time.
- Improved VMD source storage and batched curve updates for larger motions.
- Corrected add-on discovery metadata and scene initialization during installation; preserved saved settings across project upgrades.
- Added deterministic installation builds, template hash verification, output-file protection and dual-version native regression workflows.

## 3.2.0

- Renamed the add-on presentation to **BVH Motion Retargeter**.
- Polished UI labels, operator descriptions, status messages and documentation.
- Added Mixamo, UE5 Humanoid and VRM Body profiles.
- Added character templates, automatic FBX export and VRM knee compensation.
