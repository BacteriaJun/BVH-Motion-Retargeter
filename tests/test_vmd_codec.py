"""Protocol tests use independently hand-packed bytes, not codec-generated fixtures."""

import copy
import importlib.util
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tested_vmd_codec", ROOT / "bvh_to_mixamo/core/vmd_codec.py")
vmd = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = vmd
SPEC.loader.exec_module(vmd)


def fixed_name(name, length, fill=b"\x00"):
    # Include unusual but legal nonzero bytes after the first NUL terminator.
    data = name.encode("cp932")
    return data + b"\x00" + fill * (length - len(data) - 1)


def hand_fixture(version="0002", with_extension=False):
    signature = b"Vocaloid Motion Data file" if version == "0001" else b"Vocaloid Motion Data 0002"
    model_size = 10 if version == "0001" else 20
    header = signature + b"\x00" + b"\xfd" * (29 - len(signature))
    data = bytearray(header + fixed_name("モデル", model_size, b"\xfd"))
    offsets = []
    # Standalone 64-byte fixture: first columns carry each channel's controls.
    interp = bytes([20, 20, 20, 20, 20, 20, 20, 20, 107, 107, 107, 107, 107, 107, 107, 107] * 4)
    data += struct.pack("<I", 2)
    data += fixed_name("左腕", 15, b"\xfd") + struct.pack("<I3f4f", 3, -0.0, 2.5, -3, 0, 0, 0.5, 0.5) + interp
    data += fixed_name("未知指", 15) + struct.pack("<I3f4f", 1, 1, 2, 3, 0, 0, 0, 1) + interp
    offsets.append(len(data))
    data += struct.pack("<I", 1) + fixed_name("笑い", 15) + struct.pack("<If", 9, 0.75)
    offsets.append(len(data))
    data += struct.pack("<IIf3f3f24sIB", 1, 7, -32, 1, 2, 3, 0.125, 0.25, 0.5, bytes([20, 107, 20, 107] * 6), 37, 1)
    offsets.append(len(data))
    data += struct.pack("<II3f3f", 1, 11, 0.5, 0.25, 1, -1, 2, 3)
    offsets.append(len(data))
    data += struct.pack("<IIBf", 1, 13, 2, 0.075)
    offsets.append(len(data))
    data += struct.pack("<IIBI", 1, 17, 0, 2)
    data += fixed_name("左足ＩＫ", 20, b"\xfd") + b"\x01"
    data += fixed_name("右足ＩＫ", 20) + b"\x00"
    offsets.append(len(data))
    if with_extension:
        data += b"nonstandard extension\x00\xff"
    return bytes(data), offsets


class VmdProtocolTests(unittest.TestCase):
    def test_complete_manual_fixture_is_byte_exact_in_both_versions(self):
        for version in ("0001", "0002"):
            source, _ = hand_fixture(version)
            motion = vmd.loads(source)
            self.assertEqual(motion.version, version)
            self.assertEqual(motion.model_name, "モデル")
            self.assertEqual(motion.bones[0].name, "左腕")
            self.assertFalse(motion.cameras[0].perspective)
            self.assertFalse(motion.ik_frames[0].visible)
            self.assertTrue(motion.ik_frames[0].states[0].enabled)
            self.assertEqual(motion.last_frame, 17)
            self.assertEqual(vmd.dumps(motion), source)

    def test_bone_edit_preserves_all_other_records_and_opaque_extension(self):
        source, boundaries = hand_fixture(with_extension=True)
        motion = vmd.loads(source)
        motion.bones[0].position = (4, 5, 6)
        edited = vmd.dumps(motion)
        # A 12-byte bone position field is the only permitted difference.
        changed_start = 50 + 4 + 15 + 4
        self.assertEqual(edited[:changed_start], source[:changed_start])
        self.assertEqual(edited[changed_start + 12 :], source[changed_start + 12 :])
        self.assertEqual(edited[boundaries[0] :], source[boundaries[0] :])
        self.assertEqual(vmd.loads(edited).opaque_tail, b"nonstandard extension\x00\xff")

    def test_whole_suffix_omission_preserved_partial_sections_rejected(self):
        source, boundaries = hand_fixture()
        for index, end in enumerate(boundaries):
            prefix = source[:end]
            self.assertEqual(vmd.loads(prefix).section_count, index + 1)
            self.assertEqual(vmd.dumps(vmd.loads(prefix)), prefix)
            if index < 5:
                with self.assertRaises(vmd.VmdError):
                    vmd.loads(source[: end + 1])
        for length in (0, 29, 49, 51, 56, 170, len(source) - 1):
            with self.assertRaises(vmd.VmdError):
                vmd.loads(source[:length])

    def test_absurd_counts_bounded_before_iteration(self):
        source, _ = hand_fixture()
        for offset in (50,):
            data = source[:offset] + struct.pack("<I", 0xFFFFFFFF) + source[offset + 4 :]
            with self.assertRaises(vmd.VmdError):
                vmd.loads(data)

    def test_cp932_byte_limits_invalid_encoding_and_alias_collision(self):
        motion = vmd.Motion(bones=[vmd.BoneFrame("あ" * 7 + "a", 0)])
        self.assertEqual(vmd.loads(vmd.dumps(motion)).bones[0].name, "あ" * 7 + "a")
        for name in ("あ" * 8, "bone\x00hidden", "🙂"):
            motion.bones[0].name = name
            with self.assertRaises(vmd.VmdError):
                vmd.dumps(motion)
        source, _ = hand_fixture()
        invalid = source[:54] + b"\x81\x00" + source[56:]
        with self.assertRaises(vmd.VmdError):
            vmd.loads(invalid)
        # CP932 encodes the Unicode wave dash and fullwidth tilde identically.
        motion = vmd.Motion(bones=[vmd.BoneFrame("〜", 0), vmd.BoneFrame("～", 1)])
        with self.assertRaises(vmd.VmdError):
            vmd.dumps(motion)

    def test_exact_15_byte_ik_name_preserves_all_20_bytes(self):
        name = "あ" * 7 + "a"
        self.assertEqual(len(name.encode("cp932")), 15)
        raw = (
            b"Vocaloid Motion Data 0002".ljust(30, b"\x00")
            + b"model".ljust(20, b"\x00")
            + struct.pack("<5I", 0, 0, 0, 0, 0)
            + struct.pack("<IIBI", 1, 0, 1, 1)
            + name.encode("cp932")
            + b"\xfd" * 5
            + b"\x01"
        )
        motion = vmd.loads(raw)
        self.assertEqual(motion.ik_frames[0].states[0].name, name)
        self.assertEqual(vmd.dumps(motion), raw)
        # Modifying another section cannot rewrite the original IK-name padding.
        motion.bones = [vmd.BoneFrame("センター", 0)]
        self.assertEqual(vmd.dumps(motion)[-21:], raw[-21:])

    def test_duplicate_keys_invalid_numeric_and_flags_rejected(self):
        good = vmd.Motion(bones=[vmd.BoneFrame("bone", 0)])
        motion = copy.deepcopy(good)
        motion.bones.append(vmd.BoneFrame("bone", 0))
        with self.assertRaises(vmd.VmdError):
            vmd.dumps(motion)
        invalid_updates = [
            ("frame", -1),
            ("frame", True),
            ("position", (math.nan, 0, 0)),
            ("rotation", (0, 0, 0, 0)),
            ("rotation", (math.inf, 0, 0, 1)),
            ("interpolation", b"\xff" * 64),
        ]
        for field_name, value in invalid_updates:
            motion = copy.deepcopy(good)
            setattr(motion.bones[0], field_name, value)
            with self.subTest(field=field_name), self.assertRaises(vmd.VmdError):
                vmd.dumps(motion)
        with self.assertRaises(vmd.VmdError):
            vmd.dumps(vmd.Motion(cameras=[vmd.CameraFrame(0, perspective="false")]))
        with self.assertRaises(vmd.VmdError):
            vmd.dumps(vmd.Motion(shadows=[vmd.ShadowFrame(0, mode=3)]))
        with self.assertRaises(vmd.VmdError):
            vmd.dumps(vmd.Motion(bones=[], section_count=1, morphs=[vmd.MorphFrame("a", 0)]))

    def test_writer_cannot_overwrite_existing_input_or_leave_partial_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "motion.vmd"
            path.write_bytes(b"original")
            with self.assertRaises(FileExistsError):
                vmd.write_vmd(path, vmd.Motion())
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])
            vmd.write_vmd(path, vmd.Motion(), overwrite=True)
            self.assertEqual(vmd.read_vmd(path), vmd.Motion())

    def test_manual_bezier_and_slerp_truth(self):
        first = vmd.BoneFrame("bone", 0, (0, 0, 0))
        # x(t)=t^3, y(t)=1-(1-t)^3; alpha=1/8 gives factor=7/8.
        controls = bytearray(vmd.LINEAR_BONE_INTERPOLATION)
        for offset, value in zip((0, 4, 8, 12), (0, 127, 0, 127)):
            controls[offset] = value
        second = vmd.BoneFrame(
            "bone", 8, (8, 16, 24), (0, 0, math.sin(math.pi / 3), math.cos(math.pi / 3)), bytes(controls)
        )
        position, quaternion = vmd.sample_bone([second, first], 1)
        self.assertAlmostEqual(position[0], 7, places=10)
        self.assertAlmostEqual(position[1], 2, places=10)
        self.assertAlmostEqual(position[2], 3, places=10)
        self.assertAlmostEqual(quaternion[2], math.sin(math.pi / 24), places=10)
        self.assertAlmostEqual(quaternion[3], math.cos(math.pi / 24), places=10)
        # Source-key interpolation does not control this segment.
        first.interpolation = bytes(controls)
        second.interpolation = vmd.LINEAR_BONE_INTERPOLATION
        self.assertAlmostEqual(vmd.sample_bone([first, second], 1)[0][0], 1)

    def test_each_bezier_channel_is_independent(self):
        first = vmd.BoneFrame("bone", 0)
        for channel in range(4):
            controls = bytearray(vmd.LINEAR_BONE_INTERPOLATION)
            for offset, value in zip((0, 4, 8, 12), (0, 127, 0, 127)):
                controls[16 * channel + offset] = value
            second = vmd.BoneFrame(
                "bone", 8, (8, 8, 8), (0, 0, math.sin(math.pi / 3), math.cos(math.pi / 3)), bytes(controls)
            )
            position, quaternion = vmd.sample_bone([first, second], 1)
            for axis in range(3):
                self.assertAlmostEqual(position[axis], 7 if channel == axis else 1, places=10)
            expected = 7 * math.pi / 24 if channel == 3 else math.pi / 24
            self.assertAlmostEqual(quaternion[2], math.sin(expected), places=10)
            self.assertAlmostEqual(quaternion[3], math.cos(expected), places=10)

    def test_quaternion_hemisphere_normalization_endpoints_and_snapshot(self):
        a = vmd.BoneFrame("bone", 0, rotation=(0, 0, 0, 2))
        b = vmd.BoneFrame("bone", 8, rotation=(0, 0, -math.sqrt(0.5), -math.sqrt(0.5)))
        sampler = vmd.BoneSampler([a, b])
        _, quaternion = sampler.sample(4)
        self.assertAlmostEqual(quaternion[2], math.sin(math.pi / 8), places=10)
        self.assertAlmostEqual(quaternion[3], math.cos(math.pi / 8), places=10)
        self.assertEqual(sampler.sample(-5)[1], (0, 0, 0, 1))
        self.assertAlmostEqual(abs(sampler.sample(99)[1][3]), math.sqrt(0.5), places=10)
        a.position = (999, 0, 0)
        self.assertEqual(sampler.sample(0)[0], (0, 0, 0))
        with self.assertRaises(vmd.VmdError):
            sampler.sample(math.nan)


if __name__ == "__main__":
    unittest.main()
