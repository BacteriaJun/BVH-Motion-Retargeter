"""Editable VMD bone/control channels with explicit rest-basis conversion.

Independent MIT implementation. VMD does not contain rest geometry. Existing MMD
rigs or the clearly labelled canonical FK preview supply that geometry. Source
tracks and metadata are retained inside the .blend; this is not an MMD physics,
additional-transform, or native IK solver implementation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import unicodedata
from collections import defaultdict
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import vmd_codec as codec
from .animation_utils import action_fcurve_collection, iter_action_fcurves

SESSION_KEY = "bvh_vmd_session_text"
SESSION_SCHEMA = "bvh-vmd-edit-session-1"
STANDARD_LEG_IK_CONTROLS = ("左足ＩＫ", "右足ＩＫ", "左つま先ＩＫ", "右つま先ＩＫ")
MAX_IMPORTED_SAMPLES = 1_000_000
SOURCE_CHUNK_SIZE = 8192
# Swapping Y/Z changes handedness. Apply this matrix on BOTH sides of a
# rotation; treating it as a quaternion would lose the reflection.
MMD_TO_BLENDER = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))


def _positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def _frame(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise ValueError(f"{label} must be an integer between 0 and 1000000")
    return value


def _armature(armature):
    if armature is None or armature.type != "ARMATURE":
        raise ValueError("Select an MMD armature, or create the labelled VMD FK preview armature first.")
    if armature.library is not None or armature.data.library is not None:
        raise ValueError("Use a local editable armature, not linked library data.")
    return armature


def _fps(scene):
    return _positive(scene.render.fps / scene.render.fps_base, "scene frame rate")


def _set_frame(scene, frame):
    integer = math.floor(frame)
    scene.frame_set(integer, subframe=frame - integer)


def _resolve_mapping(armature, mapping=None):
    """Return {VMD name: actual Blender pose-bone name}; never guess English rigs."""
    _armature(armature)
    if mapping is not None:
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("mapping must be a nonempty {VMD name: Blender bone name} object")
        result = dict(mapping)
    else:
        result = {}
        for pose in armature.pose.bones:
            declared = getattr(getattr(pose, "mmd_bone", None), "name_j", "") or pose.bone.get("vmd_name", "")
            name = declared or pose.name
            # Japanese names are unambiguous identifiers. English Mixamo names
            # require an explicit profile instead of exporting accidental names.
            if not declared and not any(ord(ch) > 127 for ch in name):
                continue
            if name in result:
                raise ValueError(f"Ambiguous duplicate MMD name: {name}")
            result[name] = pose.name
    if not result:
        raise ValueError("No Japanese MMD bone names found. Supply an explicit VMD-to-rig bone mapping.")
    if not all(isinstance(a, str) and a and isinstance(b, str) and b for a, b in result.items()):
        raise ValueError("Bone mapping names must be nonempty strings")
    if len(set(result.values())) != len(result):
        raise ValueError("Multiple VMD tracks cannot control the same Blender bone")
    missing = [name for name in result.values() if name not in armature.pose.bones]
    if missing:
        raise ValueError("Mapped bones missing from target rig: " + ", ".join(missing[:12]))
    for name in result:
        encoded = name.encode("cp932", errors="strict")
        if len(encoded) > 15:
            raise ValueError(f"VMD bone name exceeds 15 CP932 bytes: {name}")
    return result


def _resolve_motion_mapping(armature, source_names, mapping=None):
    """Match width variants only for lookup; source names are never rewritten."""
    resolved = _resolve_mapping(armature, mapping)
    names = set(source_names)
    result = {name: actual for name, actual in resolved.items() if name in names}
    aliases = []
    # An explicit map is the user's unambiguous choice; do not expand it.
    if mapping is not None:
        return result, aliases
    used = set(result.values())
    normalized = defaultdict(list)
    for declared, actual in resolved.items():
        normalized[unicodedata.normalize("NFKC", declared)].append((declared, actual))
    for name in sorted(names - set(result)):
        candidates = normalized.get(unicodedata.normalize("NFKC", name), [])
        if not candidates:
            continue
        if len(candidates) != 1 or candidates[0][1] in used:
            raise ValueError(f"Ambiguous Unicode bone-name alias for {name}; provide an explicit one-to-one mapping.")
        declared, actual = candidates[0]
        result[name] = actual
        used.add(actual)
        aliases.append({"source_vmd_name": name, "declared_rig_name": declared, "actual_bone": actual})
    return result, aliases


def resolve_mapping(armature, mapping=None):
    """Public name binding for UI and export: VMD name -> actual rig bone."""
    return _resolve_mapping(armature, mapping)


def rest_fingerprint(armature, mapping):
    values = [["object_matrix_world", [round(float(x), 8) for row in armature.matrix_world for x in row]]]
    for name, actual in sorted(mapping.items()):
        bone = armature.data.bones[actual]
        values.append(
            [
                name,
                actual,
                bone.parent.name if bone.parent else None,
                [round(float(x), 8) for row in bone.matrix_local for x in row],
            ]
        )
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def mmd_to_pose(bone, position, quaternion_xyzw, unit_scale):
    """MMD delta in rest-world axes -> Blender matrix_basis channel axes."""
    rest = bone.matrix_local.to_3x3().normalized()
    basis = rest.inverted() @ MMD_TO_BLENDER
    q = Quaternion((quaternion_xyzw[3], *quaternion_xyzw[:3]))
    q.normalize()
    rotation = basis @ q.to_matrix() @ basis.inverted()
    return basis @ Vector(position) * unit_scale, rotation.to_quaternion().normalized()


def pose_to_mmd(bone, location, quaternion, unit_scale):
    """Exact inverse basis change; object transforms are outside the VMD rig."""
    rest = bone.matrix_local.to_3x3().normalized()
    basis = rest.inverted() @ MMD_TO_BLENDER
    rotation = basis.inverted() @ quaternion.normalized().to_matrix() @ basis
    q = rotation.to_quaternion().normalized()
    p = basis.inverted() @ Vector(location) / unit_scale
    return tuple(p), (q.x, q.y, q.z, q.w)


def _path(pose, prop):
    return pose.path_from_id(prop)


def _bone_curves(armature, actual):
    action = armature.animation_data.action
    prefix = armature.pose.bones[actual].path_from_id() + "."
    return [c for c in iter_action_fcurves(action, armature) if c.data_path.startswith(prefix)]


def _curve_digest(armature, actual):
    records = []
    action = armature.animation_data.action
    layer_state = [
        [layer.name, getattr(layer, "influence", None), getattr(layer, "mix_mode", None), getattr(layer, "mute", None)]
        for layer in getattr(action, "layers", [])
    ]
    for curve in _bone_curves(armature, actual):
        if curve.modifiers:
            # Different modifier parameters can affect the same underlying keys.
            return None
        records.append(
            [
                curve.data_path,
                curve.array_index,
                curve.mute,
                curve.extrapolation,
                bool(getattr(curve.group, "mute", False)) if curve.group else False,
                [
                    [
                        float(k.co.x),
                        float(k.co.y),
                        k.interpolation,
                        list(k.handle_left),
                        list(k.handle_right),
                        k.handle_left_type,
                        k.handle_right_type,
                    ]
                    for k in curve.keyframe_points
                ],
            ]
        )
    records.sort(key=lambda r: (r[0], r[1]))
    return hashlib.sha256(
        json.dumps([armature.pose.bones[actual].rotation_mode, layer_state, records], separators=(",", ":")).encode()
    ).hexdigest()


def _validate_animation_context(armature, *, preserve_source=False):
    transform_properties = {
        "location",
        "rotation_quaternion",
        "rotation_euler",
        "rotation_axis_angle",
        "scale",
        "delta_location",
        "delta_rotation_euler",
        "delta_rotation_quaternion",
        "delta_scale",
    }
    if preserve_source:
        # A driver can change evaluated transforms without changing a key. It
        # cannot safely be classified as an untouched imported VMD channel.
        obj = armature
        while obj is not None:
            animation = obj.animation_data
            if animation:
                for driver in animation.drivers:
                    path = driver.data_path
                    if path in transform_properties or (
                        path.startswith("pose.bones[") and path.rsplit(".", 1)[-1] in transform_properties
                    ):
                        raise ValueError(
                            "Transform drivers require an explicit new-motion bake; source-preserving VMD export cannot classify them as unchanged."
                        )
                if animation.action:
                    for curve in iter_action_fcurves(animation.action, obj):
                        if (
                            obj is armature
                            and curve.data_path.startswith("pose.bones[")
                            and curve.data_path.rsplit(".", 1)[-1] not in transform_properties
                        ):
                            raise ValueError(
                                "Source-preserving VMD export supports bone location/rotation channels only; custom properties, IK-switch edits and constraint animations need an explicit dedicated conversion."
                            )
                        if curve.data_path in transform_properties:
                            raise ValueError(
                                "Animated object placement is outside a preserved VMD rig. Bake it into explicit root channels before new-motion export."
                            )
            obj = obj.parent
    ad = armature.animation_data
    if ad:
        if any(not t.mute and len(t.strips) for t in ad.nla_tracks) and ad.use_nla:
            raise ValueError("Mute NLA strips before VMD channel editing/export; mixed takes are not implicitly baked.")
        if getattr(ad, "action_influence", 1.0) != 1.0 or getattr(ad, "action_blend_type", "REPLACE") != "REPLACE":
            raise ValueError("VMD editing/export requires an unblended active Action at full influence.")


def _write_curves(armature, action, actual, frames, locations, rotations):
    pose = armature.pose.bones[actual]
    pose.rotation_mode = "QUATERNION"
    collection = action_fcurve_collection(action, armature)
    for prop, values, count in [("location", locations, 3), ("rotation_quaternion", rotations, 4)]:
        for index in range(count):
            try:
                curve = collection.new(data_path=_path(pose, prop), index=index, action_group=actual)
            except TypeError:
                curve = collection.new(data_path=_path(pose, prop), index=index, group_name=actual)
            curve.keyframe_points.add(len(frames))
            curve.keyframe_points.foreach_set(
                "co", [v for frame, value in zip(frames, values) for v in (frame, value[index])]
            )
            linear = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
            curve.keyframe_points.foreach_set("interpolation", [linear] * len(frames))
            curve.update()


def _ik_warnings(motion, mapping):
    controls = [name for name in mapping if "ＩＫ" in name or name.upper().endswith("IK")]
    return {
        "ik_control_tracks": controls,
        "ik_switch_frames_retained": len(motion.ik_frames),
        "preview_scope": "Editable FK/control channels with original IK-switch, morph and auxiliary tracks retained.",
    }


def import_motion(
    context,
    path,
    armature,
    *,
    unit_scale=0.08,
    frame_start=1,
    replace_action=False,
    mapping=None,
    match_fps=True,
    max_samples=MAX_IMPORTED_SAMPLES,
):
    """Import into a NEW Action. Existing takes are retained when replacement is requested."""
    _armature(armature)
    unit_scale = _positive(unit_scale, "MMD unit scale")
    frame_start = _frame(frame_start, "Blender start frame")
    _validate_animation_context(armature, preserve_source=True)
    if armature.animation_data and armature.animation_data.action and not replace_action:
        raise ValueError(
            "The armature already has an Action. Choose a new preview rig or explicitly import a new take."
        )
    source = Path(path).expanduser().resolve()
    raw = source.read_bytes()
    motion = codec.loads(raw)
    names = {f.name for f in motion.bones}
    mapped, aliases = _resolve_motion_mapping(armature, names, mapping)
    if not mapped:
        raise ValueError("No VMD bone tracks match the target armature. Camera-only VMD is not a bone motion.")
    if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples <= 0:
        raise ValueError("max_samples must be a positive integer")
    last = max(f.frame for f in motion.bones if f.name in mapped)
    if last + frame_start > 1_000_000 or (last + 1) * len(mapped) > max_samples:
        raise ValueError("VMD sampled motion exceeds the bounded import budget; split the clip before importing.")
    tracks = defaultdict(list)
    for f in motion.bones:
        if f.name in mapped:
            tracks[f.name].append(f)
    scene = context.scene
    previous_frame = scene.frame_current + scene.frame_subframe
    old_fps = (scene.render.fps, scene.render.fps_base)
    old_range = (scene.frame_start, scene.frame_end)
    previous_pose = {
        name: (
            p.rotation_mode,
            p.location.copy(),
            p.rotation_quaternion.copy(),
            p.rotation_euler.copy(),
            p.scale.copy(),
        )
        for name, p in armature.pose.bones.items()
    }
    armature.animation_data_create()
    old_action = armature.animation_data.action
    old_fake_user = old_action.use_fake_user if old_action else False
    old_slot = getattr(armature.animation_data, "action_slot", None)
    action = bpy.data.actions.new(source.stem + "_VMD_edit")
    text = None
    try:
        if match_fps:
            scene.render.fps = 30
            scene.render.fps_base = 1.0
        fps = _fps(scene)
        times = [frame_start + f * fps / 30.0 for f in range(last + 1)]
        if times[-1] > 1_000_000:
            raise ValueError("Resampled VMD exceeds Blender frame range")
        armature.animation_data.action = action
        action.use_fake_user = True
        if old_action:
            old_action.use_fake_user = True
        for name, actual in mapped.items():
            sampler = codec.BoneSampler(tracks[name])
            locations, rotations = [], []
            previous_q = None
            for frame in range(last + 1):
                p, q = sampler.sample(frame)
                loc, quat = mmd_to_pose(armature.data.bones[actual], p, q, unit_scale)
                if previous_q is not None and quat.dot(previous_q) < 0:
                    quat.negate()
                previous_q = quat.copy()
                locations.append(tuple(loc))
                rotations.append(tuple(quat))
            _write_curves(armature, action, actual, times, locations, rotations)
        encoded_source = base64.b64encode(raw).decode("ascii")
        session = {
            "schema": SESSION_SCHEMA,
            "source_bytes_base64_chunks": [
                encoded_source[i : i + SOURCE_CHUNK_SIZE] for i in range(0, len(encoded_source), SOURCE_CHUNK_SIZE)
            ],
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_filename": source.name,
            "mapping": mapped,
            "name_aliases": aliases,
            "rest_fingerprint": rest_fingerprint(armature, mapped),
            "unit_scale": unit_scale,
            "frame_start": frame_start,
            "scene_fps": fps,
            "last_source_bone_frame": last,
            "source_bone_names": sorted(names),
            "baseline_curve_digests": {actual: _curve_digest(armature, actual) for actual in mapped.values()},
            **_ik_warnings(motion, mapped),
        }
        text = bpy.data.texts.new(source.stem + "_VMD_source")
        text.write(json.dumps(session, ensure_ascii=False, indent=2))
        text.use_fake_user = True
        action[SESSION_KEY] = text.name
        armature[SESSION_KEY] = text.name
        scene.frame_start = frame_start
        scene.frame_end = math.ceil(times[-1])
        scene.frame_set(frame_start)
        return {
            "action": action.name,
            "source_text": text.name,
            "source_sha256": session["source_sha256"],
            "mapped_bones": len(mapped),
            "mapped_bone_bindings": mapped,
            "name_aliases": aliases,
            "unmapped_bone_names": sorted(names - set(mapped)),
            "sampled_frames": last + 1,
            "scene_fps": fps,
            "unit_scale": unit_scale,
            "original_sections_retained": True,
            **_ik_warnings(motion, mapped),
        }
    except Exception:
        armature.animation_data.action = old_action
        if old_action:
            old_action.use_fake_user = old_fake_user
        if old_slot and old_action:
            armature.animation_data.action_slot = old_slot
        if text:
            bpy.data.texts.remove(text)
        bpy.data.actions.remove(action)
        scene.render.fps, scene.render.fps_base = old_fps
        scene.frame_start, scene.frame_end = old_range
        for name, state in previous_pose.items():
            p = armature.pose.bones[name]
            p.rotation_mode, p.location, p.rotation_quaternion, p.rotation_euler, p.scale = state
        _set_frame(scene, previous_frame)
        raise


def _session(armature):
    _armature(armature)
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        raise ValueError("The armature has no active Action")
    name = action.get(SESSION_KEY)
    text = bpy.data.texts.get(name) if isinstance(name, str) else None
    if text is None:
        raise ValueError("This Action has no preserved VMD source. Use explicit FK-to-VMD export for new motions.")
    session = json.loads(text.as_string())
    if session.get("schema") != SESSION_SCHEMA:
        raise ValueError("Unsupported or damaged VMD editing session")
    if "source_bytes_base64_chunks" in session:
        if "source_bytes_base64" in session:
            raise ValueError("Ambiguous preserved VMD source encodings")
        chunks = session["source_bytes_base64_chunks"]
        if (
            not isinstance(chunks, list)
            or not chunks
            or not all(isinstance(c, str) and 0 < len(c) <= SOURCE_CHUNK_SIZE for c in chunks)
        ):
            raise ValueError("Invalid preserved VMD source chunks")
        if sum(map(len, chunks)) > 4 * ((codec.MAX_FILE_BYTES + 2) // 3):
            raise ValueError("Preserved VMD source exceeds the codec file budget")
        encoded_source = "".join(chunks)
    else:
        # Pre-chunk sessions remain readable. Never rewrite their original file.
        encoded_source = session.get("source_bytes_base64")
        if not isinstance(encoded_source, str):
            raise ValueError("Preserved VMD source encoding is missing")
        if len(encoded_source) > 4 * ((codec.MAX_FILE_BYTES + 2) // 3):
            raise ValueError("Preserved VMD source exceeds the codec file budget")
    raw = base64.b64decode(encoded_source, validate=True)
    if hashlib.sha256(raw).hexdigest() != session["source_sha256"]:
        raise ValueError("Preserved VMD source checksum mismatch")
    mapping = _resolve_mapping(armature, session["mapping"])
    if rest_fingerprint(armature, mapping) != session["rest_fingerprint"]:
        raise ValueError(
            "Rig rest geometry, hierarchy or object transform changed after VMD import. Reimport against the revised rig."
        )
    return session, codec.loads(raw), raw


def _read_pose_channels(pose):
    if any(not math.isfinite(v) for row in pose.matrix_basis for v in row):
        raise ValueError(f"Non-finite pose channels on {pose.name}")
    location, rotation, scale = pose.matrix_basis.decompose()
    if max(abs(v - 1.0) for v in scale) > 1e-5:
        raise ValueError(f"VMD has no bone scale channel: {pose.name}")
    return location, rotation


def _sample_channel_tracks(context, armature, mapping, last_frame, scene_start, fps, scale):
    """Evaluate each time once, then gather every mapped control at that time."""
    if not mapping:
        return []
    records = {name: [] for name in mapping}
    previous = {}
    poses = {name: armature.pose.bones[actual] for name, actual in mapping.items()}
    for frame in range(last_frame + 1):
        _set_frame(context.scene, scene_start + frame * fps / 30.0)
        for name, pose in poses.items():
            p, q = _read_pose_channels(pose)
            p, q = pose_to_mmd(pose.bone, p, q, scale)
            if name in previous and sum(a * b for a, b in zip(previous[name], q)) < 0:
                q = tuple(-v for v in q)
            previous[name] = q
            records[name].append(
                codec.BoneFrame(
                    name=name, frame=frame, position=p, rotation=q, interpolation=codec.LINEAR_BONE_INTERPOLATION
                )
            )
    # Keep the original track-major record ordering; only evaluation is batched.
    return [record for track in records.values() for record in track]


def _sample_channel_track(context, armature, actual, name, last_frame, scene_start, fps, scale):
    return _sample_channel_tracks(context, armature, {name: actual}, last_frame, scene_start, fps, scale)


def export_motion(
    context, path, armature, *, overwrite=False, frame_start=None, frame_end=None, bone_names=None, unit_scale=None
):
    """Patch changed bone tracks, preserving unedited records and ALL other sections."""
    session, motion, raw = _session(armature)
    _validate_animation_context(armature, preserve_source=True)
    scene = context.scene
    for actual in session["mapping"].values():
        _read_pose_channels(armature.pose.bones[actual])
    if abs(_fps(scene) - session["scene_fps"]) > 1e-6:
        raise ValueError("Scene FPS changed since VMD import. Restore the import FPS or use explicit new FK export.")
    if unit_scale is not None and abs(_positive(unit_scale, "MMD unit scale") - session["unit_scale"]) > 1e-9:
        raise ValueError("Roundtrip export must use the recorded import scale; use new FK export to change units.")
    if frame_start is not None and frame_start != session["frame_start"]:
        raise ValueError(
            "Source-preserving export keeps the original time origin; cropping requires a separate new-motion export."
        )
    last = session["last_source_bone_frame"]
    if frame_end is not None:
        _frame(frame_end, "Blender end frame")
        requested = math.floor((frame_end - session["frame_start"]) * 30 / session["scene_fps"] + 1e-7)
        if requested < last:
            raise ValueError(
                "Source-preserving export cannot trim bone tracks while retaining untrimmed extra sections."
            )
        last = requested
    mapping = session["mapping"]
    if bone_names is not None:
        chosen = set(bone_names)
        if not chosen <= set(mapping.values()):
            raise ValueError("Export selection contains bones not mapped in the preserved VMD session")
    else:
        chosen = set(mapping.values())
    digests = {actual: _curve_digest(armature, actual) for actual in chosen}
    changed = {
        name: actual
        for name, actual in mapping.items()
        if actual in chosen
        and (
            last != session["last_source_bone_frame"]
            or digests[actual] != session["baseline_curve_digests"].get(actual)
            or digests[actual] is None
        )
    }
    if (last + 1) * len(changed) > MAX_IMPORTED_SAMPLES:
        raise ValueError("VMD export exceeds the bounded sample budget")
    previous_frame = scene.frame_current + scene.frame_subframe
    try:
        replacement = _sample_channel_tracks(
            context, armature, changed, last, session["frame_start"], session["scene_fps"], session["unit_scale"]
        )
        if changed:
            motion.bones = [b for b in motion.bones if b.name not in changed] + replacement
        # Raw bytes are used when untouched, including original float bit patterns.
        payload = codec.dumps(motion) if changed else raw
        codec.write_vmd(path, motion, overwrite=overwrite)
    finally:
        _set_frame(scene, previous_frame)
    return {
        "path": str(Path(path)),
        "changed_bone_names": sorted(changed),
        "unchanged_bone_names": sorted(set(session["source_bone_names"]) - set(changed)),
        "all_nonbone_sections_preserved": True,
        "untouched_file_byte_identical": not changed,
        "source_sha256": session["source_sha256"],
        "output_sha256": hashlib.sha256(payload).hexdigest(),
        "sample_rate": 30,
        "unit_scale": session["unit_scale"],
        "native_mmd_playback_verified": False,
        "scope": "FK/control channel export. Edited tracks are sampled at 30fps; original extra tracks remain byte-preserved.",
    }


def _validate_new_fk_visual_scope(armature, mapping):
    """New FK export samples channels; refuse unbaked scene/constraint motion."""
    transform_properties = {
        "location",
        "rotation_quaternion",
        "rotation_euler",
        "rotation_axis_angle",
        "scale",
        "delta_location",
        "delta_rotation_euler",
        "delta_rotation_quaternion",
        "delta_scale",
    }
    obj = armature
    while obj is not None:
        if any(not constraint.mute for constraint in obj.constraints):
            raise ValueError("Bake object/parent constraints into explicit root channels before new FK VMD export.")
        animation = obj.animation_data
        if animation:
            for driver in animation.drivers:
                if driver.data_path in transform_properties:
                    raise ValueError(
                        "Bake animated object/parent transforms and transform drivers into root channels before new FK VMD export."
                    )
            if animation.action and any(
                curve.data_path in transform_properties for curve in iter_action_fcurves(animation.action, obj)
            ):
                raise ValueError(
                    "Bake animated object/parent placement into explicit root channels before new FK VMD export."
                )
            for track in animation.nla_tracks:
                if not track.mute and len(track.strips):
                    raise ValueError("Bake/mute parent NLA tracks before new FK VMD export.")
        if obj.parent is not None and obj.parent_type == "BONE":
            parent_animation = obj.parent.animation_data
            if parent_animation and (parent_animation.action or parent_animation.drivers):
                raise ValueError(
                    "Bake animated bone-parent placement into explicit root channels before new FK VMD export."
                )
        obj = obj.parent
    for actual in mapping.values():
        if any(not constraint.mute for constraint in armature.pose.bones[actual].constraints):
            raise ValueError("Bake mapped bone constraints/IK into pose channels before new FK VMD export.")


def export_fk_motion(
    context,
    path,
    armature,
    mapping,
    *,
    unit_scale=0.08,
    frame_start=None,
    frame_end=None,
    overwrite=False,
    model_name="BVH Retargeter",
    disable_standard_leg_ik=True,
    ik_control_names=None,
):
    """New VMD from explicit FK mapping. No arbitrary-rig rest-pose retarget claim."""
    _armature(armature)
    _validate_animation_context(armature)
    scale = _positive(unit_scale, "MMD unit scale")
    if not isinstance(disable_standard_leg_ik, bool):
        raise ValueError("disable_standard_leg_ik must be a boolean")
    if not isinstance(ik_control_names, (list, tuple, type(None))):
        raise ValueError("IK control names must be a list of distinct nonempty strings")
    controls = list(STANDARD_LEG_IK_CONTROLS if ik_control_names is None else ik_control_names)
    if not all(isinstance(n, str) and n for n in controls) or len(set(controls)) != len(controls):
        raise ValueError("IK control names must be a list of distinct nonempty strings")
    switches = (
        [codec.IKFrame(0, True, [codec.IKState(n, False) for n in controls])]
        if disable_standard_leg_ik and controls
        else []
    )
    # Validate header/name/switch fields before any potentially large bake.
    codec.dumps(codec.Motion(model_name=model_name, ik_frames=switches))
    mapping = _resolve_mapping(armature, mapping)
    _validate_new_fk_visual_scope(armature, mapping)
    if not armature.animation_data or not armature.animation_data.action:
        raise ValueError("The source rig has no active Action")
    scene = context.scene
    start = _frame(scene.frame_start if frame_start is None else frame_start, "Blender start frame")
    end = _frame(scene.frame_end if frame_end is None else frame_end, "Blender end frame")
    if end < start:
        raise ValueError("End frame precedes start frame")
    fps = _fps(scene)
    last = math.floor((end - start) * 30 / fps + 1e-6)
    if (last + 1) * len(mapping) > MAX_IMPORTED_SAMPLES:
        raise ValueError("VMD export exceeds the bounded sample budget")
    previous_frame = scene.frame_current + scene.frame_subframe
    try:
        bones = _sample_channel_tracks(context, armature, mapping, last, start, fps, scale)
        motion = codec.Motion(model_name=model_name, bones=bones, ik_frames=switches)
        codec.write_vmd(path, motion, overwrite=overwrite)
    finally:
        _set_frame(scene, previous_frame)
    return {
        "path": str(Path(path)),
        "bones": len(mapping),
        "sampled_frames": last + 1,
        "sample_rate": 30,
        "source_fps": fps,
        "source_frame_range": [start, end],
        "unit_scale": scale,
        "disabled_ik_controls": controls if disable_standard_leg_ik else [],
        "native_mmd_playback_verified": False,
        "notes": [
            "Target settings: match MMD rest pose, bone names, units and IK/FK state.",
            "New FK motion sets standard leg/toe IK off at frame0 by default; custom models may use different control names.",
            "New motion tracks: mapped bone position and rotation at 30 fps.",
        ],
    }


def create_preview_armature(context, motion=None, *, name="VMD_FK_Preview", unit_scale=0.08):
    """Canonical A-pose FK reference, not rest geometry recovered from the VMD."""
    scale = _positive(unit_scale, "MMD unit scale")
    if context.mode != "OBJECT":
        raise ValueError("Switch to Object Mode before creating a VMD preview armature")
    # Coordinates are hand-authored MMD units. VMD contains no body proportions.
    rows = [
        ("全ての親", None, (0, 0, 0), (0, 0.6, 0)),
        ("センター", "全ての親", (0, 9, 0), (0, 10, 0)),
        ("グルーブ", "センター", (0, 9.2, 0), (0, 10.2, 0)),
        ("腰", "グルーブ", (0, 9.5, 0), (0, 10.2, 0)),
        ("下半身", "腰", (0, 9.5, 0), (0, 8.4, 0)),
        ("上半身", "腰", (0, 10, 0), (0, 12.5, 0)),
        ("上半身2", "上半身", (0, 12.5, 0), (0, 14.2, 0)),
        ("首", "上半身2", (0, 14.2, 0), (0, 15.3, 0)),
        ("頭", "首", (0, 15.3, 0), (0, 17.6, 0)),
    ]
    for side, sign in [("左", 1), ("右", -1)]:

        def reflect(p):
            return (p[0] * sign, p[1], p[2])

        for suffix, parent, head, tail in [
            ("肩", "上半身2", (0.5, 14.1, 0), (1.8, 14, 0)),
            ("腕", side + "肩", (1.8, 14, 0), (4.3, 12.6, 0)),
            ("ひじ", side + "腕", (4.3, 12.6, 0), (6.5, 11.2, 0)),
            ("手首", side + "ひじ", (6.5, 11.2, 0), (7.2, 10.8, 0)),
            ("足", "下半身", (1, 9.1, 0), (1, 5.1, 0.25)),
            ("ひざ", side + "足", (1, 5.1, 0.25), (1, 0.9, 0)),
            ("足首", side + "ひざ", (1, 0.9, 0), (1, 0.5, -1.3)),
            ("つま先", side + "足首", (1, 0.5, -1.3), (1, 0.5, -1.8)),
            ("足ＩＫ", "全ての親", (1, 0.9, 0), (1, 0.9, -0.8)),
            ("つま先ＩＫ", side + "足ＩＫ", (1, 0.5, -1.3), (1, 0.5, -1.8)),
        ]:
            rows.append((side + suffix, parent, reflect(head), reflect(tail)))
        for finger, z in [("親指", -0.4), ("人指", -0.2), ("中指", 0), ("薬指", 0.2), ("小指", 0.4)]:
            start = 0 if finger == "親指" else 1
            for segment in range(start, 3 if finger == "親指" else 4):
                i = segment - start
                key = side + finger + str(segment)
                parent = side + "手首" if i == 0 else side + finger + str(segment - 1)
                head = reflect((7.1 + i * 0.38, 10.9 - i * 0.12, z))
                tail = reflect((7.48 + i * 0.38, 10.78 - i * 0.12, z))
                rows.append((key, parent, head, tail))
    data = bpy.data.armatures.new(name)
    armature = bpy.data.objects.new(name, data)
    context.collection.objects.link(armature)
    for obj in context.selected_objects:
        obj.select_set(False)
    armature.select_set(True)
    context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, parent, head, tail in rows:
        bone = data.edit_bones.new(bone_name)
        bone.head = MMD_TO_BLENDER @ Vector(head) * scale
        bone.tail = MMD_TO_BLENDER @ Vector(tail) * scale
        if parent:
            bone.parent = data.edit_bones[parent]
        bone.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for bone in data.bones:
        bone["vmd_name"] = bone.name
        bone.use_deform = "ＩＫ" not in bone.name and bone.name not in {"全ての親", "センター", "グルーブ", "腰"}
    armature["bvh_vmd_preview"] = True
    armature["bvh_vmd_unit_scale"] = scale
    armature["bvh_vmd_preview_notice"] = (
        "Generic FK reference skeleton with editable motion and IK control tracks."
    )
    armature.show_in_front = True
    data.display_type = "STICK"
    return armature
