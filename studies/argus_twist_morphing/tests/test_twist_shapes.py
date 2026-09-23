import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus_twist_morphing.twist_shapes import (  # noqa: E402
    control_point_twist,
    smooth_window,
    twist_schedule_metrics,
)


class TwistShapeTests(unittest.TestCase):
    def test_window_is_zero_outside_region(self):
        self.assertEqual(smooth_window(0.50, 0.60, 0.95), 0.0)
        self.assertEqual(smooth_window(0.98, 0.60, 0.95), 0.0)

    def test_window_reaches_one_interior(self):
        self.assertAlmostEqual(smooth_window(0.775, 0.60, 0.95), 1.0)

    def test_twist_returns_to_zero_at_boundaries(self):
        args = (
            0.60,
            0.95,
            [0.60, 0.6875, 0.775, 0.8625, 0.95],
            [-2.0, -2.0, -2.0, -2.0, -2.0],
        )
        self.assertEqual(control_point_twist(0.60, *args), 0.0)
        self.assertEqual(control_point_twist(0.95, *args), 0.0)

    def test_control_point_interpolation_interior(self):
        result = control_point_twist(
            0.775,
            0.60,
            0.95,
            [0.60, 0.6875, 0.775, 0.8625, 0.95],
            [0.0, -1.0, -3.0, -2.0, 0.0],
        )
        self.assertAlmostEqual(result, -3.0)

    def test_schedule_metrics(self):
        metrics = twist_schedule_metrics(
            [0.60, 0.70, 0.80],
            [0.0, -2.0, -1.0],
        )
        self.assertAlmostEqual(metrics["max_abs_twist_deg"], 2.0)
        self.assertAlmostEqual(metrics["max_adjacent_delta_deg"], 2.0)
        self.assertAlmostEqual(metrics["max_spanwise_slope_deg_per_eta"], 20.0)


if __name__ == "__main__":
    unittest.main()


