# VMD editing and export

[English overview](../README.md) · [中文概览](../README_zh-CN.md)

VMD stores motion tracks. The add-on imports bone/control tracks into an editable Blender Action and embeds the original VMD in the `.blend`. Source-preserving export updates edited mapped tracks while retaining other bones, morphs, camera, light, shadow and IK-switch records.

## Choose a rig

- **Reference Preview / 参考骨架预览** creates a labelled reference armature with body, finger and foot-IK control names. It provides FK/control-track editing with defined proportions and an A-pose.
- **Selected MMD Rig / 所选 MMD 骨架** uses a compatible rig with Japanese names from `mmd_bone.name_j`, `bone['vmd_name']` or actual bone names. The separate [MMD Tools](https://github.com/MMD-Blender/blender_mmd_tools) extension can import a PMX model.

VMD carries no rest skeleton. The corresponding MMD/PMX model environment supplies model-specific IK, append transforms, facial deformation and physics. Original IK-switch records are retained during source-preserving export.

Full-width finger numbers such as `左人指１` match `左人指1` through lookup normalization. Original names and bytes are retained. Exact names take priority. Ambiguous aliases or two tracks targeting one bone cause an error; explicit mappings use the supplied names. Thumb indices keep their numeric identity: `親指１` maps to thumb 1.

## Refine an existing VMD

1. Choose **VMD**, a source file and a rig mode, then click **Import Editable VMD / 导入可编辑 VMD**. Import creates a separate Action.
2. Import defaults to **30 fps**, VMD's timebase. The API can retain a different scene rate and place keys at equivalent times: VMD frame 30 becomes Blender frame 61 at 60 fps with start frame 1.
3. Edit bone/control location and quaternion animation, or create a denoised copy. Save the `.blend` to retain the source and edit-session metadata.
4. Select **Preserve Imported VMD / 保留原 VMD 数据** and export to a new path.

An untouched export is byte-identical to the source, including interpolation and retained vendor tail bytes. Edited tracks are resampled at 30 Hz with linear VMD segments. Integer-frame poses are retained; between-frame motion follows that sampling. Unchanged mapped bones, unmapped bones and nonbone sections keep their original records.

The default conversion is **0.08 Blender units per MMD unit**. The session records the chosen value and reuses it on export. Bone/control transforms are interpreted in armature-local space. The original object transform and rest skeleton must remain unchanged for source-preserving export.

## Export a new FK motion

Choose **New FK Motion / 新建 FK 动作** for mapped BVH/Mixamo or other compatible rig animation. The mapping is `{Japanese_VMD_name: Blender_bone_name}`. Match target rest axes, units, root/center placement and names before export.

The exporter samples FK/control channels at 30 Hz using the scene's `fps / fps_base`. Bake visual constraints into pose channels first. New FK export defaults to a frame-0 model-visibility/IK record disabling `左足ＩＫ`, `右足ＩＫ`, `左つま先ＩＫ` and `右つま先ＩＫ`. The API offers `disable_standard_leg_ik=False` or explicit `ik_control_names=[...]`. Source-preserving mode retains the original IK-switch section.

A new FK motion contains the exported mapped channels and its IK configuration. Existing morph, camera and IK-switch data can be retained through the source-preserving workflow.

## Export requirements

| Condition | Required action |
| --- | --- |
| Missing/ambiguous mapping, overlong CP932 names, or non-editable rig | Correct the mapping or rig. Names must fit the VMD fields. |
| Changed rest pose, hierarchy or object transform in an imported session | Reimport against that rig or export a deliberate new motion. |
| Source-preserving session with transform drivers, animated object placement, active NLA mixing or partial Action influence | Bake the intended pose to a plain Action and create a new motion, or restore the imported session. |
| Animated custom properties or constraint influence in source-preserving mode | Edit supported bone/control channels; binary IK switches are retained from the source. |
| New FK export with object/parent motion, object-transform drivers or active object/mapped-bone constraints | Bake motion into pose channels before exporting. Pose-channel drivers can be sampled in this mode. |
| Scene FPS changed after import | Restore the recorded import FPS, or create a new FK motion at the intended timing. |
| Bone scale channels | Remove animated scale or use a revised rig; VMD represents location and rotation. |
| Cropped body animation with untrimmed retained sections | Use new-motion export for a cropped take. |
| Existing output file | Choose a new path or explicitly enable overwrite. |

Import accepts body/control motion with at least one mapped track. The default dense-sampling budget is **1,000,000 bone × frame samples** and Blender frames 0–1,000,000; `max_samples` can change the sample budget through the API. Failed imports restore the active Action, FPS/range and pose state. A newly created reference rig is removed when its import fails.

## Developer interface

```python
from bvh_to_mixamo.core.vmd_blender import (
    create_preview_armature, import_motion, export_motion, export_fk_motion,
)

rig = create_preview_armature(context, unit_scale=0.08)
import_motion(context, source_path, rig, unit_scale=0.08)
# Edit/key the active Action, then retain the other original VMD tracks.
export_motion(context, new_path, rig)
# Or create a new FK motion with an explicit mapping.
export_fk_motion(context, new_fk_path, rig, {"センター": "mixamorig:Hips"})
```

The coordinate conversion is `(x,y,z) → (x,z,y)`, combined with each bone's rest orientation. Rotation matrices are conjugated across the reflected basis. Source data is embedded as bounded Base64 chunks in a Blender Text datablock; older single-string sessions remain readable.

## Verified behaviour

Native tests cover reflected axes, non-axis-aligned finger rests, byte-exact untouched export, one-bone edits with other sections retained, `.blend` save/reopen, 24/60 fps timing, resource bounds and failed-import rollback. Protocol tests cover binary/interpolation handling and independent MMD Tools reader/writer interchange.

Two real captures, 287/499 frames with 52 bone tracks each, were checked for full-width finger aliases, byte-exact untouched export, cleanup copies and saved-file reopening. The corresponding native-runtime and target-application status is recorded in [release checks](release-readiness.md).
