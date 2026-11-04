# 4.0.0 RC1 release preparation

This is an **unreleased local candidate**. Preparing this source and its CI does not publish a GitHub release, push a branch, or certify target-application playback.

## Scope

- VMD → editable Blender Action → preserved VMD, including original nonbone tracks and unmapped records.
- Explicitly mapped new FK VMD export from compatible rigs. New FK files disable standard leg/toe IK; calibrate the target MMD model rest pose and units.
- Generic reference FK geometry for reviewing VMD without a PMX model. Source IK switches are preserved; this reference does not evaluate native MMD IK, append transforms, morphs or physics.
- Bounded rotation cleanup, optional video-confirmed short root-packet repair, and scale-aware export diagnostics. Original objects/Actions are retained.
- Mixamo and generic UE4/UE5 humanoid FBX profiles, sampled every frame with no exporter key reduction.
- Legacy 4.2 Actions and modern layered Actions share the same access layer.

## Evidence boundaries

Local native tests run on macOS arm64 Blender 4.2.0 and 5.1.2. The prepared Linux CI workflow has not run on GitHub during this task. Windows runtime, MikuMikuDance playback and Unreal Editor import are separate acceptance checks; FBX reimport in Blender and an independent VMD reader are not substitutes for them.

The user supplied two real VMD captures during preparation. Their untouched roundtrips, alias mapping, editable copies and nonbone preservation are checked privately. Customer VMD/BVH/video/FBX, their raw content and external reference implementations must stay outside public source and installation ZIPs. Public tests generate original synthetic fixtures.

## Before a public release

1. Review the local candidate and run the committed CI on the intended release commit.
2. Play the edited VMD on the intended MMD models, including IK-enabled legs and fingers. Review source intent and the target model's rest/IK configuration.
3. Import animation-only and character FBX into the actual UE4/UE5 projects; select/retarget to the intended Skeleton and check root motion, scale and frame rate.
4. Validate the supported customer operating systems and compare the source and candidate animations visually.
5. Review the changelog, exact installation ZIP, source commit and checksums. The release asset must be built from that reviewed source; never include private validation directories.

## Reproduce

```sh
python scripts/fetch_templates.py
python -m unittest discover -s tests -v
python -m compileall -q bvh_to_mixamo scripts tests
python scripts/build_release.py --output /absolute/path/candidate.zip
```

For native commands see `.github/workflows/ci.yml`. Every Blender test uses factory startup, disabled automatic scripts and a nonzero Python-error exit code. Installation tests additionally use fresh `BLENDER_USER_CONFIG` and `BLENDER_USER_SCRIPTS` directories. `scripts/fetch_blender.py --verify-reports ...` validates reports independently of process exit status.

The installation builder rejects unreviewed modules, capture/media files and symlinks, verifies all six original template hashes, includes the MIT attribution and produces deterministic ZIP bytes. The source's `bl_info` marks RC1; remove that candidate label only after acceptance of the release commit.
