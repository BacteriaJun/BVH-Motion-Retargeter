# VMD transport and interpolation

The MIT add-on implements this codec independently using Python's standard
library. It does not bundle, import or require MMD Tools or nanoem. Upstream
implementations were consulted to check binary field layout and interoperability,
not copied into the implementation.

## Public interface

`core.vmd_codec` is importable without Blender:

- `Motion(model_name='', bones=[], morphs=[], cameras=[], lights=[], shadows=[],
  ik_frames=[], version='0002', section_count=6)` contains flat record lists.
  The dataclass defaults create a fresh list per instance.
- `BoneFrame(name, frame, position=(0,0,0), rotation=(0,0,0,1),
  interpolation=LINEAR_BONE_INTERPOLATION)` uses **xyzw** quaternion order.
- Other records: `MorphFrame`, `CameraFrame`, `LightFrame`, `ShadowFrame`,
  `IKFrame(frame, visible=True, states=[])`, `IKState(name, enabled=True)`.
- `read_vmd(path)`, `loads(bytes)`, `dumps(motion)` and
  `write_vmd(path, motion, overwrite=False)` handle binary data. A writer
  validates the complete result before creating an atomic output. It refuses
  an existing destination unless explicitly allowed to replace it.
- `BoneSampler(frames).sample(frame)` validates and snapshots one named track
  once, then samples repeatedly. `sample_bone(frames, frame)` is a convenience
  wrapper for one-off sampling.
- `bone_interpolation(curves)` encodes four `(x1,y1,x2,y2)` Bezier control sets
  in X, Y, Z and rotation order. Controls are integers in 0..127.

Use `copy.deepcopy(motion)` before editing. A `BoneSampler` is a snapshot;
construct a new sampler after changing keys.

## File facts and explicit choices

VMD carries motion, **not a rest skeleton**. Frame numbers are at 30fps. The
codec keeps MMD coordinates and units; a Blender bridge must explicitly convert
rest axes, coordinates and scale. Renaming bones does not establish compatible
rest geometry or IK semantics.

Supported header signatures are modern `Vocaloid Motion Data 0002` with a
20-byte model field and legacy `Vocaloid Motion Data file` with a 10-byte model
field. Both have a 30-byte signature field.

Bone records use a 15-byte CP932 name, uint32 frame, float32 position/quaternion
and 64 interpolation bytes. The ordered sections are bones, morphs, camera,
light, self-shadow and model visibility/IK switches. A shadow distance remains
its raw file scalar; no renderer-specific distance conversion is applied.

The codec preserves record order, complete omitted section suffixes, nonzero
name/header padding and non-unit valid quaternions. Bytes after all six known
sections are retained in `Motion.opaque_tail`, without interpreting unknown
extension semantics. Partial counts/records are rejected rather than treated
as missing sections. Bone-only legacy files are accepted at a complete section
boundary; this does not imply every external application accepts every prefix.

Names are never truncated or replaced. Invalid/unencodable CP932, non-reversible
Unicode aliases and overlong names are rejected to avoid silent binding changes.
Bone/morph fields allow at most 15 bytes. IK storage is 20 bytes, but this codec
limits semantic IK names to 15 bytes for compatibility with readers that only
interpret that prefix. The remaining five raw storage bytes, including nonzero
padding after an exact 15-byte name, are retained byte-for-byte. Unsupported
longer semantic names fail explicitly.

Duplicate frame numbers within a named track are ambiguous and rejected.
Nonfinite numbers, zero quaternions, invalid flags and record counts inconsistent
with remaining bytes fail. File size is limited to 128MiB and total records
(including IK states) to 1,000,000. These are documented resource bounds, not
claims about the VMD specification's theoretical maximum.

## Interpolation

The destination key owns the curve for the preceding segment. Each position
axis has an independent Bezier curve; rotation has one curve driving a
shortest-arc normalized quaternion SLERP. The implementation inverts cubic x
with bounded bisection and evaluates cubic y. It holds the first/last pose
outside the track's key range. Read/write never normalize source quaternions;
normalization occurs only when interpreting a pose for sampling.

Blender's component quaternion F-curves are not equivalent to this SLERP.
A bridge that samples to per-frame keys must disclose its temporal sampling
error between keys; binary roundtrip fidelity alone does not validate that
animation playback matches MMD at every subframe.

## Validation and limits

Pure tests use hand-packed byte fixtures independent of the writer, both header
variants, all six sections, CP932/padding, unknown-bone and non-bone preservation,
malformed counts/truncation, writer protection and closed-form Bezier/SLERP cases.

The development evidence additionally checks modern generated VMD files with the
upstream MMD Tools pure reader, reads its saved outputs back, and checks all six
section types. The external reference module stays outside the repository and
installable add-on. This is protocol interoperability on synthetic data, **not**
customer DiMocap VMD validation or an actual MikuMikuDance application playback
test. Legacy headers were checked against nanoem's declared layout and hand
fixtures; the modern-only external MMD Tools reader did not test legacy files.

## Primary references

- [MMD Tools upstream VMD binary structures](https://github.com/MMD-Blender/blender_mmd_tools/blob/main/mmd_tools/core/vmd/__init__.py)
- [MMD Tools upstream interpolation import](https://github.com/MMD-Blender/blender_mmd_tools/blob/main/mmd_tools/core/vmd/importer.py)
- [MMD Tools upstream interpolation export](https://github.com/MMD-Blender/blender_mmd_tools/blob/main/mmd_tools/core/vmd/exporter.py)
- [nanoem upstream header sizes and signatures](https://github.com/hkrn/nanoem/blob/main/nanoem/nanoem_p.h)

No third-party implementation is included by these links. Evidence records the
reference file's SHA256 because branch URLs can change over time.
