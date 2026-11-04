# VMD editing and export

VMD is a motion file, not a model or rest skeleton. The add-on can now bring
VMD bone/control tracks into an editable Blender Action and export the edited
motion again. The source motion is retained inside the `.blend`, so refining a
finger or root track does not erase unrelated face, camera, light, IK-switch or
unrecognised bone tracks.

## Two rig choices

- **Selected MMD armature:** use a rig whose pose-bone Japanese MMD names are
  available as `mmd_bone.name_j`, `bone['vmd_name']`, or the actual Japanese bone
  names. A rig imported by the separate [MMD Tools](https://github.com/MMD-Blender/blender_mmd_tools)
  extension can supply model geometry. This add-on does not include that GPL
  extension or a third-party character model.
- **New VMD FK preview:** the add-on creates its own hand-authored, labelled
  reference skeleton with standard body, finger and foot-IK control names. It
  is useful when only the motion file is available. Its proportions and A-pose
  are assumptions, not geometry recovered from the VMD. Foot-IK control tracks
  can be edited, but this reference does not implement MMD's native IK, physics,
  append transforms or facial deformation. Use the original model's rig for
  final model-specific checks.

Fullwidth finger numbers such as `左人指１` can match a reference bone named
`左人指1` using Unicode NFKC **for lookup only**. The original VMD names and
bytes are retained. Exact names take priority; ambiguous normalization or two
source tracks targeting one bone causes refusal. An explicit mapping never
receives inferred alias expansion. Thumb indices keep their numeric identity;
`親指１` maps to reference thumb 1, not thumb 0.

Unknown tracks remain in the retained source even when the reference rig cannot
preview them. A VMD with no matching body/control tracks is explicitly refused
by the bone importer; a camera-only VMD is not silently converted into a body
motion.

## Refine an existing VMD

1. Keep the original file. Import onto the selected compatible MMD rig, or create
   the labelled FK preview. Import creates a separate Action. Replacing an
   existing active take requires an explicit choice and retains that old Action.
2. The default import sets the scene to **30fps**, the VMD timebase. An API option
   can keep another scene rate and place keys at equivalent times. For example,
   VMD frame 30 is Blender frame 61 when importing at 60fps with start frame 1.
3. Edit bone/control location and quaternion curves, and insert animation keys
   as in normal Blender animation editing. Save the `.blend` to keep the embedded
   original source and edit-session metadata. Source bytes are stored as bounded
   Base64 chunks in a multiline Text datablock, avoiding quadratic insertion of
   a multi-megabyte single line. Older single-string sessions remain readable.
4. Export a **new VMD path**. Source-preserving export patches only the mapped
   tracks whose curves changed. Edited tracks are sampled at 30fps with linear
   VMD segments. Unchanged bone records, unmapped bones and all nonbone sections
   retain their original bytes.

If nothing was edited, the exported file is byte-identical to the source,
including interpolation and opaque vendor tail bytes. Edited tracks retain
integer-frame poses; their between-frame interpolation is a sampled
approximation. Blender's component-quaternion curves are not the same as VMD's
SLERP. Very fast rotations and subframe work need a separate playback review.

The default unit conversion is **0.08 Blender units per MMD unit**. This is an
editable import convention, not a scale encoded by VMD. The session records the
chosen value; re-export uses that same value. Bone transforms are interpreted in
armature-local space. Object placement, object scale and parent motion are not
silently baked into a VMD root track.

## Export a new motion from another rig

The explicit FK exporter accepts a mapping from Japanese VMD names to actual
Blender bone names. The product's Mixamo-to-MMD mapping can supply those names.
It samples the active rig's FK/control channels at 30Hz using the scene's
`fps / fps_base`; a 24fps or 60fps source is not mistaken for a 30fps frame index.

This is a new VMD motion, so no face/camera/physics tracks are invented. To keep
MMD model leg IK from overriding newly exported FK legs, new FK export defaults
to a frame-0 model-display/IK record disabling the standard `左足ＩＫ`, `右足ＩＫ`,
`左つま先ＩＫ` and `右つま先ＩＫ` controls. `disable_standard_leg_ik=False` opts out;
`ik_control_names=[...]` supplies different explicit control names for a custom
model. These switches belong only to a **new** motion. Source-preserving VMD
export never replaces the original IK-switch section. A name
mapping alone cannot calibrate a different model's rest pose. Check A/T-pose,
body axes, root/center placement and target MMD IK/FK configuration on the actual
model. Bake visual constraints into pose channels before exporting a rig whose
motion depends on runtime constraints. This exporter is not an IK or physics
baker. New FK export refuses animated object/parent placement, object transform
drivers, unmuted object constraints and unmuted constraints on mapped bones.
This prevents a successful export that silently loses walking root motion or
an unbaked IK solution. Explicit pose-channel drivers can be sampled in the
new-motion path; source-preserving mode still refuses them.

## Explicit refusal conditions

- Missing/ambiguous mapped names, overlong CP932 names or a non-editable rig.
- A changed rest skeleton, hierarchy or object transform in a source-preserving
  edit session. Reimport against the revised rig or use an explicit new-motion
  export instead.
- Transform drivers, animated object placement, active NLA mixing, or partial
  Action influence during a source-preserving edit. These can change a pose
  without changing the recorded keys. Animated custom properties and constraint
  influence are also refused; editing Blender IK-switch properties is not a
  supported way to modify the retained binary IK-switch section. They must not be misclassified as an
  untouched source track. MMD custom IK-switch properties are retained as source
  data; native IK playback equivalence is not claimed.
- A changed scene frame rate during source-preserving re-export. Retiming only
  body keys while keeping camera/morph/IK timestamps would desynchronise the
  file. Restore the recorded import FPS or intentionally export a new FK motion.
- Bone scale channels: VMD cannot encode arbitrary bone scale.
- Trimming only body tracks while preserving untrimmed extra sections. Use a
  separate new-motion export for a deliberate cropped take.
- Excessive dense sampling. Import defaults to at most **1,000,000 bone × frame
  samples**, with a `max_samples` API override, and a Blender frame domain of
  0–1,000,000. A valid uint32 VMD frame can exceed this engineering budget and is
  rejected before creating an Action or changing scene FPS.
- Existing destination files, unless overwrite is explicitly selected.

A failed import rolls back the active Action, frame rate/range and pose state.
The UI's newly created preview rig must also be removed if its subsequent import
fails. Originals are never modified by the default workflow.

## Developer interfaces

All maps are `{VMD_name: actual_Blender_bone_name}`. `unit_scale` is positive.

```python
from bvh_to_mixamo.core.vmd_blender import (
    create_preview_armature, import_motion, export_motion, export_fk_motion,
)

rig = create_preview_armature(context, unit_scale=0.08)
report = import_motion(context, source_path, rig, unit_scale=0.08)
# Edit/key the active Action, then preserve unrelated original VMD tracks.
report = export_motion(context, new_path, rig)
# Or export a new FK motion using an explicit target-name mapping.
report = export_fk_motion(context, new_path, rig, {"センター": "mixamorig:Hips"})
```

`mmd_to_pose` and `pose_to_mmd` change coordinates with the reflection
`(x,y,z) -> (x,z,y)` and the bone's rest orientation. Rotation matrices are
conjugated on both sides of that basis change. The handedness reflection is
never treated as an ordinary rotation quaternion.

## Verification and remaining acceptance work

`tests/blender/test_vmd_roundtrip.py` runs in actual isolated Blender. Its
synthetic fixture specifies the geometry and known rotations independently;
it checks reflected axes, non-axis-aligned finger rests, untouched binary
roundtrip, one-bone edits with all other tracks preserved, `.blend` save/reopen,
24/60fps timing, refusal budgets and failure rollback.

The codec also has separate pure binary/interpolation tests and independent
MMD Tools reader/writer checks. These do not establish native MMD playback,
PMX deformation/IK/physics equivalence or arbitrary-vendor compatibility. Two user-provided VMD captures (287/499 frames, 52 bone tracks each) were additionally checked privately for full-width finger-name editing, byte-exact untouched export, cleanup copies and saved-file reopening. Their original IK switches remain enabled and preserved; the generic FK preview does not evaluate that native IK. Keep file fidelity, preview geometry and target-application playback claims separate.
