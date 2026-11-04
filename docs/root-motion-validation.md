# Root motion and FBX validation

The Unreal profiles generate a generic humanoid hierarchy with a root bone for the target engine's Skeleton and retarget workflow.

## Horizontal travel in world axes

`_split_pelvis_motion_to_root` samples the evaluated pelvis position in Blender world coordinates. It allocates world X/Y travel to the root and retains vertical body motion in the pelvis. Pose translations are converted through each bone's rest and parent transforms.

New root bones start at the armature/model origin `(0, 0, 0)`. Existing roots retain their authored rest head and tail. The allocation holds the first sampled root-head world height; this follows the model origin. Physical floor alignment is configured with the target character.

Native regressions cover nonidentity object rotation, constant uniform scale and animated object rotation/translation. Sampled pelvis, head, hand, foot and index-base world positions remain within numerical tolerance. FBX export samples every frame with key reduction disabled.

## Processing requirements

Root allocation bakes integer-frame FK transforms into a separate Action. An already split root, existing root keys, active constraints/NLA/drivers, multiple Action layers, a nonidentity unkeyed root pose or nonuniform/animated object scale needs baking or the original Action before allocation.

FBX preflight checks finite animation/pose data and large root discontinuities in the selected export range. Review discontinuities against the source motion. The short root-repair tool uses trusted samples on both sides of a confirmed anomaly; damaged terminal segments require a reviewed range.

## Native tests

Run from the repository root, writing results outside the source tree:

```sh
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python tests/blender/test_cleanup.py -- --output /absolute/new/cleanup-results
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python tests/blender/test_fbx_profiles.py -- --output /absolute/new/fbx-results
```

The tests generate original synthetic motion with known transforms.

- `test_cleanup.py`: original Action/pose/file preservation; root-location and finger preservation; rotation-error bounds; Euler full-turn neighbourhoods; zero-strength Bezier preservation; scoped root-gap repair; invalid tails, object transforms and nonfinite data.
- `test_fbx_profiles.py`: Mixamo/UE4/UE5 export and Blender FBX reimport; names, hierarchy, sample counts and marker trajectories; world-axis root allocation; transformed/animated objects; output protection; frame/subframe restoration; repeated root-allocation detection.

Native Blender export/reimport is recorded separately from the intended Unreal Editor project check in [release checks](release-readiness.md).
