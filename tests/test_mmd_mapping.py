import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "mmd_mapping", Path(__file__).parents[1] / "bvh_to_mixamo/core/mmd_mapping.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.rig = SimpleNamespace(
            data=SimpleNamespace(
                bones={
                    "mixamorig:Hips": object(),
                    "mixamorig:LeftHandIndex1": object(),
                    "mixamorig:LeftHandThumb1": object(),
                    "mixamorig:LeftHandThumb2": object(),
                    "mixamorig:Spine1": object(),
                }
            )
        )

    def test_explicit_target_digit_conventions_and_preserved_thumb_indices(self):
        full = m.mixamo_mapping(self.rig)
        ascii_ = m.mixamo_mapping(self.rig, "ASCII")
        self.assertEqual(full["左人指１"], "mixamorig:LeftHandIndex1")
        self.assertEqual(ascii_["左人指1"], "mixamorig:LeftHandIndex1")
        self.assertEqual(full["左親指０"], "mixamorig:LeftHandThumb1")
        self.assertEqual(full["左親指１"], "mixamorig:LeftHandThumb2")
        self.assertIn("上半身2", full)
        self.assertNotIn("上半身２", full)
        self.assertTrue(all(len(name.encode("cp932")) <= 15 for name in full))

    def test_missing_root_or_unknown_convention_rejected(self):
        with self.assertRaises(ValueError):
            m.mixamo_mapping(SimpleNamespace(data=SimpleNamespace(bones={})))
        with self.assertRaises(ValueError):
            m.mixamo_mapping(self.rig, "GUESS")


if __name__ == "__main__":
    unittest.main()
