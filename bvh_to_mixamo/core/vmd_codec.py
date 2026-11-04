"""Independent, standard-library VMD codec and bone interpolation.

VMD stores model-relative motion in MMD units, at 30 frames per second. It
contains no rest skeleton. This module neither guesses a skeleton nor converts
coordinates. Original record order, name padding and omitted tail sections are
preserved. Format facts were cross-checked against the upstream implementations
listed in docs/vmd-format-notes.md; no third-party implementation is bundled.
"""

from __future__ import annotations

import bisect
import math
import numbers
import os
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

VMD_FPS = 30
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_RECORDS = 1_000_000
UINT32_MAX = (1 << 32) - 1
_SIGNATURES = {"0001": b"Vocaloid Motion Data file", "0002": b"Vocaloid Motion Data 0002"}


class VmdError(ValueError):
    """Invalid or unsupported VMD data. No partial output should be accepted."""


def bone_interpolation(curves: Sequence[Sequence[int]]) -> bytes:
    """Encode four (x1,y1,x2,y2) curves for X/Y/Z/rotation, values 0..127.

    Each 16-byte block has its own curve in the first column. The remaining
    bytes also populate the redundant interleaved representation used by MMD.
    """
    if len(curves) != 4 or any(len(c) != 4 for c in curves):
        raise VmdError("Bone interpolation needs four four-control curves")
    for curve in curves:
        if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 127 for v in curve):
            raise VmdError("Bezier controls must be integers in 0..127")
    interleaved = [curves[channel][control] for control in range(4) for channel in range(4)]
    return bytes(value for channel in range(4) for value in (interleaved[channel:] + [0] * channel))


LINEAR_BONE_INTERPOLATION = bone_interpolation([(20, 20, 107, 107)] * 4)


@dataclass
class BoneFrame:
    name: str
    frame: int
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    interpolation: bytes = LINEAR_BONE_INTERPOLATION
    raw_name: bytes | None = field(default=None, repr=False, compare=False)


@dataclass
class MorphFrame:
    name: str
    frame: int
    weight: float = 0.0
    raw_name: bytes | None = field(default=None, repr=False, compare=False)


@dataclass
class CameraFrame:
    frame: int
    distance: float = 0.0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    interpolation: bytes = bytes([20, 107, 20, 107] * 6)
    view_angle: int = 45
    perspective: bool = True


@dataclass
class LightFrame:
    frame: int
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    direction: tuple[float, float, float] = (0.0, -1.0, 0.0)


@dataclass
class ShadowFrame:
    frame: int
    mode: int = 0
    distance: float = 0.0  # The raw file scalar; no renderer-specific conversion.


@dataclass
class IKState:
    name: str
    enabled: bool = True
    raw_name: bytes | None = field(default=None, repr=False, compare=False)


@dataclass
class IKFrame:
    frame: int
    visible: bool = True
    states: list[IKState] = field(default_factory=list)


@dataclass
class Motion:
    model_name: str = ""
    bones: list[BoneFrame] = field(default_factory=list)
    morphs: list[MorphFrame] = field(default_factory=list)
    cameras: list[CameraFrame] = field(default_factory=list)
    lights: list[LightFrame] = field(default_factory=list)
    shadows: list[ShadowFrame] = field(default_factory=list)
    ik_frames: list[IKFrame] = field(default_factory=list)
    version: str = "0002"
    section_count: int = 6
    opaque_tail: bytes = b""
    raw_header: bytes | None = field(default=None, repr=False, compare=False)
    raw_model_name: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def last_frame(self) -> int:
        sections = (self.bones, self.morphs, self.cameras, self.lights, self.shadows, self.ik_frames)
        return max((record.frame for section in sections for record in section), default=0)


def _uint(value, label, maximum=UINT32_MAX):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise VmdError(f"{label} must be an integer in 0..{maximum}")
    return value


def _number(value, label):
    if not isinstance(value, numbers.Real) or isinstance(value, bool) or not math.isfinite(value):
        raise VmdError(f"{label} must be finite")
    # struct.pack rejects overflow too, but validating here gives a useful error.
    if abs(value) > 3.4028234663852886e38:
        raise VmdError(f"{label} is outside float32 range")
    return float(value)


def _vector(value, size, label):
    if not isinstance(value, (tuple, list)) or len(value) != size:
        raise VmdError(f"{label} must contain {size} numbers")
    return tuple(_number(v, label) for v in value)


def _quaternion(value):
    q = _vector(value, 4, "Quaternion xyzw")
    if math.hypot(*q) < 1e-12:
        raise VmdError("Quaternion must be nonzero")
    return q


def _bool(value, label):
    if not isinstance(value, bool):
        raise VmdError(f"{label} must be a boolean")
    return int(value)


def _decode_name(raw, label, allow_empty=False):
    try:
        name = raw.split(b"\x00", 1)[0].decode("cp932", errors="strict")
    except UnicodeDecodeError as exc:
        raise VmdError(f"{label} is not valid CP932; refusing a lossy name conversion") from exc
    if not name and not allow_empty:
        raise VmdError(f"{label} must not be empty")
    return name


def _name_bytes(name, size, label, raw=None, allow_empty=False, semantic_size=None):
    if not isinstance(name, str) or "\x00" in name or (not name and not allow_empty):
        raise VmdError(f"{label} must be a non-NUL name")
    try:
        encoded = name.encode("cp932", errors="strict")
    except UnicodeEncodeError as exc:
        raise VmdError(f"{label} cannot be represented in CP932") from exc
    if encoded.decode("cp932") != name:
        raise VmdError(f"{label} is a non-reversible CP932 alias; choose an unambiguous name")
    byte_limit = size if semantic_size is None else semantic_size
    if len(encoded) > byte_limit:
        raise VmdError(f"{label} exceeds its {byte_limit}-byte CP932 field; names are never truncated")
    # Preserve nonzero padding and CP932 aliases when the decoded name is unchanged.
    if isinstance(raw, bytes) and len(raw) == size and _decode_name(raw[:byte_limit], label, allow_empty) == name:
        return raw
    return encoded.ljust(size, b"\x00")


def _interpolation(value, size, label):
    if not isinstance(value, bytes) or len(value) != size:
        raise VmdError(f"{label} must be exactly {size} bytes")
    # Only the defined control entries are semantically constrained. Padding is opaque.
    indices = [16 * channel + offset for channel in range(4) for offset in (0, 4, 8, 12)] if size == 64 else range(24)
    if any(value[i] > 127 for i in indices):
        raise VmdError(f"{label} control values must lie in 0..127")
    return value


def _records(records, cls, label):
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise VmdError(f"{label} must be a list with at most {MAX_RECORDS} records")
    if not all(isinstance(record, cls) for record in records):
        raise VmdError(f"{label} contains a wrong record type")
    return records


class _Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.offset = 0
        self.record_count = 0

    @property
    def remaining(self):
        return len(self.data) - self.offset

    def take(self, size, label):
        if size > self.remaining:
            raise VmdError(f"Truncated {label} at byte {self.offset}")
        start = self.offset
        self.offset += size
        return self.data[start : self.offset].tobytes()

    def unpack(self, fmt, label):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt), label))

    def count(self, minimum_size, label):
        count = self.unpack("<I", label + " count")[0]
        self.record_count += count
        if self.record_count > MAX_RECORDS or count > self.remaining // minimum_size:
            raise VmdError(f"{label} count exceeds file bounds or record budget")
        return count


def loads(data: bytes) -> Motion:
    """Read a supported VMD, preserving exact order/padding/complete section prefix.

    EOF at a section boundary is accepted for old exporters. Partial counts or
    partial records fail. Bytes after all six known sections remain opaque.
    """
    if not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES:
        raise VmdError(f"VMD input must be bytes no larger than {MAX_FILE_BYTES}")
    reader = _Reader(data)
    header = reader.take(30, "header")
    signature = header.split(b"\x00", 1)[0]
    version = next((key for key, value in _SIGNATURES.items() if signature == value), None)
    if version is None:
        raise VmdError("Unsupported VMD signature")
    raw_model = reader.take(10 if version == "0001" else 20, "model name")
    motion = Motion(
        _decode_name(raw_model, "Model name", True),
        version=version,
        section_count=0,
        raw_header=header,
        raw_model_name=raw_model,
    )
    # Bone count is mandatory. Later sections can be omitted only as a whole suffix.
    for section, size in enumerate((111, 23, 61, 28, 9, 9)):
        if section and not reader.remaining:
            break
        count = reader.count(size, ("Bone", "Morph", "Camera", "Light", "Shadow", "IK")[section])
        motion.section_count += 1
        for _ in range(count):
            if section == 0:
                name = reader.take(15, "bone name")
                values = reader.unpack("<I3f4f64s", "bone frame")
                motion.bones.append(
                    BoneFrame(_decode_name(name, "Bone name"), values[0], values[1:4], values[4:8], values[8], name)
                )
            elif section == 1:
                name = reader.take(15, "morph name")
                frame, weight = reader.unpack("<If", "morph frame")
                motion.morphs.append(MorphFrame(_decode_name(name, "Morph name"), frame, weight, name))
            elif section == 2:
                values = reader.unpack("<If3f3f24sIB", "camera frame")
                if values[10] not in (0, 1):
                    raise VmdError("Camera perspective flag must be 0 or 1")
                motion.cameras.append(
                    CameraFrame(values[0], values[1], values[2:5], values[5:8], values[8], values[9], values[10] == 0)
                )
            elif section == 3:
                values = reader.unpack("<I3f3f", "light frame")
                motion.lights.append(LightFrame(values[0], values[1:4], values[4:7]))
            elif section == 4:
                frame, mode, distance = reader.unpack("<IBf", "shadow frame")
                motion.shadows.append(ShadowFrame(frame, mode, distance))
            else:
                frame, visible = reader.unpack("<IB", "IK frame header")
                if visible not in (0, 1):
                    raise VmdError("Visibility flag must be 0 or 1")
                state_count = reader.count(21, "IK state")
                states = []
                for _ in range(state_count):
                    name = reader.take(20, "IK state name")
                    enabled = reader.unpack("<B", "IK enabled")[0]
                    if enabled not in (0, 1):
                        raise VmdError("IK state flag must be 0 or 1")
                    states.append(IKState(_decode_name(name[:15], "IK name"), bool(enabled), name))
                motion.ik_frames.append(IKFrame(frame, bool(visible), states))
    if motion.section_count == 6:
        motion.opaque_tail = reader.take(reader.remaining, "opaque extension")
    # Share validation with serialization; do not normalize rotations on read.
    _validate(motion)
    return motion


def _validate(motion):
    if not isinstance(motion, Motion) or not isinstance(motion.version, str) or motion.version not in _SIGNATURES:
        raise VmdError("Expected a Motion with a supported VMD version")
    if (
        not isinstance(motion.section_count, int)
        or isinstance(motion.section_count, bool)
        or not 1 <= motion.section_count <= 6
    ):
        raise VmdError("section_count must be between 1 and 6")
    _name_bytes(motion.model_name, 10 if motion.version == "0001" else 20, "Model name", motion.raw_model_name, True)
    if not isinstance(motion.opaque_tail, bytes) or (motion.opaque_tail and motion.section_count != 6):
        raise VmdError("Opaque data can follow only all six known sections")
    sections = (
        (motion.bones, BoneFrame),
        (motion.morphs, MorphFrame),
        (motion.cameras, CameraFrame),
        (motion.lights, LightFrame),
        (motion.shadows, ShadowFrame),
        (motion.ik_frames, IKFrame),
    )
    total = 0
    for section, (records, cls) in enumerate(sections):
        _records(records, cls, cls.__name__)
        if section >= motion.section_count and records:
            raise VmdError("A populated section cannot be omitted by section_count")
        total += len(records)
        names = {}
        duplicates = set()
        for record in records:
            _uint(record.frame, "Frame")
            if isinstance(record, (BoneFrame, MorphFrame)):
                encoded = _name_bytes(record.name, 15, "Track name", record.raw_name)
                key = (record.name, record.frame)
                # CP932 permits distinct Unicode strings to encode identically.
                canonical = encoded.split(b"\x00", 1)[0]
                if canonical in names and names[canonical] != record.name:
                    raise VmdError("Different track names collide in CP932")
                names[canonical] = record.name
            else:
                key = record.frame
            if key in duplicates:
                raise VmdError("Duplicate frame in one VMD track is ambiguous")
            duplicates.add(key)
            if isinstance(record, BoneFrame):
                _vector(record.position, 3, "Bone position")
                _quaternion(record.rotation)
                _interpolation(record.interpolation, 64, "Bone interpolation")
            elif isinstance(record, MorphFrame):
                _number(record.weight, "Morph weight")
            elif isinstance(record, CameraFrame):
                _number(record.distance, "Camera distance")
                _vector(record.position, 3, "Camera position")
                _vector(record.rotation, 3, "Camera Euler rotation")
                _interpolation(record.interpolation, 24, "Camera interpolation")
                _uint(record.view_angle, "Camera field of view")
                _bool(record.perspective, "Camera perspective")
            elif isinstance(record, LightFrame):
                _vector(record.color, 3, "Light color")
                _vector(record.direction, 3, "Light direction")
            elif isinstance(record, ShadowFrame):
                _uint(record.mode, "Shadow mode", 2)
                _number(record.distance, "Shadow distance")
            else:
                _bool(record.visible, "Model visibility")
                _records(record.states, IKState, "IK states")
                total += len(record.states)
                state_names = set()
                for state in record.states:
                    encoded = _name_bytes(state.name, 20, "IK name", state.raw_name, semantic_size=15)
                    # Most MMD readers interpret only the first 15 IK-name bytes.
                    if len(state.name.encode("cp932")) > 15:
                        raise VmdError("IK name exceeds interoperable 15-byte name limit")
                    canonical = encoded.split(b"\x00", 1)[0]
                    if canonical in state_names:
                        raise VmdError("Duplicate IK state name")
                    state_names.add(canonical)
                    _bool(state.enabled, "IK enabled")
    if total > MAX_RECORDS:
        raise VmdError("VMD record budget exceeded")


def dumps(motion: Motion) -> bytes:
    """Serialize valid motion without sorting, normalizing or dropping sections."""
    _validate(motion)
    header = _SIGNATURES[motion.version].ljust(30, b"\x00")
    if isinstance(motion.raw_header, bytes) and len(motion.raw_header) == 30:
        if motion.raw_header.split(b"\x00", 1)[0] == _SIGNATURES[motion.version]:
            header = motion.raw_header
    chunks = [
        header,
        _name_bytes(
            motion.model_name, 10 if motion.version == "0001" else 20, "Model name", motion.raw_model_name, True
        ),
    ]
    sections = (motion.bones, motion.morphs, motion.cameras, motion.lights, motion.shadows, motion.ik_frames)
    for section, records in enumerate(sections[: motion.section_count]):
        chunks.append(struct.pack("<I", len(records)))
        for record in records:
            if section == 0:
                chunks.extend(
                    (
                        _name_bytes(record.name, 15, "Bone name", record.raw_name),
                        struct.pack(
                            "<I3f4f64s", record.frame, *record.position, *record.rotation, record.interpolation
                        ),
                    )
                )
            elif section == 1:
                chunks.extend(
                    (
                        _name_bytes(record.name, 15, "Morph name", record.raw_name),
                        struct.pack("<If", record.frame, record.weight),
                    )
                )
            elif section == 2:
                chunks.append(
                    struct.pack(
                        "<If3f3f24sIB",
                        record.frame,
                        record.distance,
                        *record.position,
                        *record.rotation,
                        record.interpolation,
                        record.view_angle,
                        0 if record.perspective else 1,
                    )
                )
            elif section == 3:
                chunks.append(struct.pack("<I3f3f", record.frame, *record.color, *record.direction))
            elif section == 4:
                chunks.append(struct.pack("<IBf", record.frame, record.mode, record.distance))
            else:
                chunks.append(struct.pack("<IBI", record.frame, int(record.visible), len(record.states)))
                for state in record.states:
                    chunks.extend(
                        (
                            _name_bytes(state.name, 20, "IK name", state.raw_name, semantic_size=15),
                            struct.pack("<B", int(state.enabled)),
                        )
                    )
    chunks.append(motion.opaque_tail)
    if sum(map(len, chunks)) > MAX_FILE_BYTES:
        raise VmdError("Serialized VMD exceeds file budget")
    return b"".join(chunks)


def read_vmd(path: str | Path) -> Motion:
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise VmdError("VMD exceeds file budget")
    with path.open("rb") as source:
        return loads(source.read(MAX_FILE_BYTES + 1))


def write_vmd(path: str | Path, motion: Motion, overwrite: bool = False) -> Path:
    """Write a complete validated file atomically; an existing path is protected."""
    if not isinstance(overwrite, bool):
        raise VmdError("overwrite must be a boolean")
    payload = dumps(motion)
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".vmd-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # Atomic create-if-absent; cannot race an existing source.
        return path
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def bezier_factor(time_fraction: float, controls: Sequence[int]) -> float:
    """Invert monotone cubic x(t), then evaluate y(t), with bounded bisection."""
    if len(controls) != 4 or any(not isinstance(v, int) or not 0 <= v <= 127 for v in controls):
        raise VmdError("Bezier controls must be four bytes in 0..127")
    if not isinstance(time_fraction, numbers.Real) or not math.isfinite(time_fraction):
        raise VmdError("Interpolation time must be finite")
    x = min(1.0, max(0.0, float(time_fraction)))
    if x in (0.0, 1.0):
        return x
    x1, y1, x2, y2 = (v / 127.0 for v in controls)
    if x1 == y1 and x2 == y2:
        return x

    def cubic(t, a, b):
        return 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t * t * b + t**3

    low, high = 0.0, 1.0
    for _ in range(48):
        middle = (low + high) * 0.5
        if cubic(middle, x1, x2) < x:
            low = middle
        else:
            high = middle
    return cubic((low + high) * 0.5, y1, y2)


def _unit_quaternion(q):
    q = _quaternion(q)
    length = math.hypot(*q)
    return tuple(value / length for value in q)


def _slerp(first, second, fraction):
    first, second = _unit_quaternion(first), _unit_quaternion(second)
    dot = sum(a * b for a, b in zip(first, second))
    if dot < 0:
        second = tuple(-value for value in second)
        dot = -dot
    dot = min(1.0, max(-1.0, dot))
    if dot > 0.9995:
        return _unit_quaternion(tuple((1 - fraction) * a + fraction * b for a, b in zip(first, second)))
    angle = math.acos(dot)
    gain_first = math.sin((1 - fraction) * angle) / math.sin(angle)
    gain_second = math.sin(fraction * angle) / math.sin(angle)
    return tuple(gain_first * a + gain_second * b for a, b in zip(first, second))


class BoneSampler:
    """Validated immutable track snapshot for repeated O(log n) sampling."""

    def __init__(self, frames: Sequence[BoneFrame]):
        if not frames or not all(isinstance(item, BoneFrame) for item in frames):
            raise VmdError("Sampling requires a nonempty BoneFrame sequence")
        for item in frames:
            _uint(item.frame, "Frame")
            _name_bytes(item.name, 15, "Bone name", item.raw_name)
        if len({item.name for item in frames}) != 1:
            raise VmdError("BoneSampler accepts one named track at a time")
        ordered = sorted(frames, key=lambda item: item.frame)
        self.times = tuple(_uint(item.frame, "Frame") for item in ordered)
        if len(set(self.times)) != len(self.times):
            raise VmdError("Duplicate frame in one VMD track is ambiguous")
        self.positions = tuple(_vector(item.position, 3, "Bone position") for item in ordered)
        self.rotations = tuple(_unit_quaternion(item.rotation) for item in ordered)
        self.interpolations = tuple(_interpolation(item.interpolation, 64, "Bone interpolation") for item in ordered)

    def sample(self, frame: float):
        if not isinstance(frame, numbers.Real) or isinstance(frame, bool) or not math.isfinite(frame):
            raise VmdError("Sample time must be finite")
        index = bisect.bisect_right(self.times, frame)
        if index == 0 or index == len(self.times):
            key = 0 if index == 0 else -1
            return self.positions[key], self.rotations[key]
        alpha = (frame - self.times[index - 1]) / (self.times[index] - self.times[index - 1])
        interpolation = self.interpolations[index]
        factors = [bezier_factor(alpha, tuple(interpolation[16 * c + o] for o in (0, 4, 8, 12))) for c in range(4)]
        first, second = self.positions[index - 1 : index + 1]
        position = tuple(a + (b - a) * factor for a, b, factor in zip(first, second, factors))
        return position, _slerp(self.rotations[index - 1], self.rotations[index], factors[3])


def sample_bone(frames: Sequence[BoneFrame], frame: float):
    """Sample a track; use BoneSampler for repeated samples of the same track.

    The destination key owns interpolation for the preceding segment. Rotation
    uses shortest-arc SLERP, rather than four independent component curves.
    Queries outside the track hold the first or last key.
    """
    return BoneSampler(frames).sample(frame)
