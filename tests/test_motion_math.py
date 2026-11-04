import importlib.util
import math
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "motion_math", Path(__file__).parents[1] / "bvh_to_mixamo/core/motion_math.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MotionMathTests(unittest.TestCase):
    def test_analytic_signal_denoising_and_angle_budget(self):
        truth = [math.radians(8 * math.sin(i / 30 * math.pi)) for i in range(121)]
        noisy = [m.exp_vector((v + math.radians(3 * (-1) ** i), 0, 0)) for i, v in enumerate(truth)]
        out, r = m.denoise_quaternions(noisy, 30, strength=1.0, cap_degrees=3.0)
        def score(values):
            return sum(
            m.distance_degrees(q, m.exp_vector((t, 0, 0))) ** 2 for q, t in zip(values[5:-5], truth[5:-5])
        )
        self.assertLess(score(out), score(noisy) * 0.6)
        self.assertLessEqual(r["max_correction_degrees"], 3.000001)
        self.assertEqual(out[:2], noisy[:2])
        self.assertEqual(out[-2:], noisy[-2:])

    def test_full_turn_quaternions_and_sign_invariance(self):
        values = [m.exp_vector((0, 0, math.radians(i * 5))) for i in range(121)]
        flipped = [tuple(v * (-1 if i % 2 else 1) for v in q) for i, q in enumerate(values)]
        a, _ = m.denoise_quaternions(values, 30)
        b, _ = m.denoise_quaternions(flipped, 30)
        self.assertLess(max(m.distance_degrees(x, y) for x, y in zip(a, b)), 1e-5)
        self.assertLess(max(m.distance_degrees(x, y) for x, y in zip(a, values)), 1e-5)

    def test_real_impact_and_protected_event_not_smoothed(self):
        values = [m.exp_vector((0, 0, 0 if i < 30 else math.pi / 2)) for i in range(61)]
        out, r = m.denoise_quaternions(values, 30, strength=1)
        self.assertEqual(out, values)
        self.assertEqual(r["large_angular_steps"], [30])

    def test_known_gap_recovers_quadratic_and_preserves_scope(self):
        truth = [(0.01 * i, 0.2 + 0.0001 * i * i, 0) for i in range(61)]
        bad = list(truth)
        for i in range(20, 23):
            bad[i] = (truth[i][0], truth[i][1] + 0.2, 0)
        out, r = m.reconstruct_short_gap(bad, 30, 20, 22, 1, True)
        self.assertLess(max(math.dist(a, b) for a, b in zip(out, truth)), 1e-10)
        self.assertEqual(out[:20], bad[:20])
        self.assertEqual(out[23:], bad[23:])
        self.assertLess(r["max_root_change_L"], 0.21)

    def test_gap_requires_evidence_and_brackets_and_finite_budgets(self):
        values = [(0, 0, 0)] * 61
        for args in [
            (20, 22, 1, False, 0.3),
            (58, 60, 1, True, 0.3),
            (20, 25, 1, True, 0.3),
            (20, 22, float("nan"), True, 0.3),
            (20, 22, 1, "false", 0.3),
            (20, 22, 1, True, float("nan")),
        ]:
            with self.assertRaises(ValueError):
                m.reconstruct_short_gap(values, 30, *args)


if __name__ == "__main__":
    unittest.main()
