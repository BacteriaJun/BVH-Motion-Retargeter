# Changelog

All notable user-visible changes are documented here.

## Unreleased — 4.0.0 RC1

- Added editable VMD import, embedded original-session data, generic FK reference rigs and source-preserving export of all VMD sections.
- Added explicit new FK VMD export, target mapping, 30 Hz resampling and standard leg/toe IK-disable flags.
- Added full-width/ASCII name alias matching without altering original records; reject ambiguous bindings.
- Added bounded SO(3) cleanup copies, video-confirmed short root-packet repair and scale-aware export diagnostics.
- Added UE4 profile and repaired Unreal horizontal root allocation using world axes; preserve body motion and start new roots at model origin.
- Fixed layered Action access across Blender 4.2 and 5.x, stale export-object selection, export subframe restoration and silent driver/unsupported-edit loss.
- Replaced the unavailable FCurve simplify method with bounded reduction for linear baked channels; nonlinear curves and original takes are retained.
- Repaired short-BVH export ranges and preserved seconds when importing into a different scene frame rate.
- Removed quadratic long-line source-text storage and per-key curve-update bottlenecks; batch processing preserves frozen VMD output bytes.
- Added atomic output protection, package file allowlists, template hash verification, MIT attribution and deterministic archives.
- Added synthetic protocol/native/operator/install regressions and a prepared dual-version headless CI matrix. Target-application acceptance remains separate.

### Previous source maintenance

- Added the maintainable v3.2.0 source tree to the repository.
- Added reproducible release packaging, repository checks, and GitHub Actions CI.
- Moved development documentation and tests outside the installable add-on.
- Added checksum-verified retrieval for large bundled FBX templates.
- Aligned the Blender extension manifest license with the repository's MIT license.

## 3.2.0

- Renamed the add-on presentation to **BVH Motion Retargeter**.
- Polished UI labels, operator descriptions, status messages, and documentation.
- Added Mixamo, UE5 Humanoid, and VRM Body profiles.
- Added character templates, automatic FBX export, and VRM knee compensation.
- Removed the bundled personal VRM test asset from the release package.
