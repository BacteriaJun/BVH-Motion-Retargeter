# 4.0.0 release checks

## Feature and verification record

| Area | Verified behaviour / status |
| --- | --- |
| VMD | Editable bone/control Actions; byte-exact untouched export; changed-track export retains other bone and nonbone records; saved sessions reopen. |
| Real VMD files | Two captures, 287/499 frames and 52 bone tracks each: untouched byte roundtrip, full-width finger aliases, editable cleanup copies and saved-file reopening. |
| Cleanup | Separate object/Action; default root-location, finger and IK-rotation preservation; bounded filtering and two-sided short root repair. |
| FBX / root | Mixamo/UE4/UE5 native Blender export/reimport; world-axis root allocation; sampled body-marker trajectories retained. |
| Local native runtime | macOS arm64, Blender 4.2.0 and 5.1.2: VMD, cleanup, FBX, retargeting, character binding, operators, language switching, template migration, adversarial cases and isolated installation. |
| Interface / templates | Auto, 简体中文 and English; Black/White templates plus Custom; discontinued template choices migrate to White. |
| Build | Version agreement, package-file allowlist, two SHA256-verified templates, MIT attribution and deterministic archives. |
| GitHub CI | Linux and Windows jobs run Blender 4.2.0 and 5.1.2. Each commit’s result and native reports are available in GitHub Actions. |
| Target-application checks | MikuMikuDance/PMX playback and Unreal Editor import remain to be checked in the intended model/project. |

The reference armature edits FK/control tracks and retains source IK-switch fields. The corresponding MMD model environment supplies model-specific IK, append transforms, facial deformation and physics.

## Reproduce repository checks and build

```sh
python -m pip install ruff==0.14.4
python scripts/fetch_templates.py
ruff check .
python -m compileall -q bvh_to_mixamo scripts tests
python -m unittest discover -s tests -v
python scripts/build_release.py --output /absolute/path/bvh_motion_retargeter_v4.0.0_release.zip
```

Run native tests using the commands in [`ci.yml`](../.github/workflows/ci.yml). They use factory startup and isolated user directories for installation checks. Validate the resulting reports:

```sh
python scripts/fetch_blender.py --verify-reports /absolute/path/verification --expected-version 4.2.0
```

Repeat with 5.1.2. Record the source commit, final ZIP SHA256 and matching native reports for the release. The installation ZIP contains runtime code and the two character templates; development tests, local captures and verification outputs remain outside it.
