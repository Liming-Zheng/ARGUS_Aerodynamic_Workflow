import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus_morphing.morphing_shapes import (  # noqa: E402
    control_point_amplitude,
    control_point_metrics,
    spanwise_amplitude,
)


class MorphingShapeTests(unittest.TestCase):
    def test_control_point_interpolation(self):
        self.assertAlmostEqual(
            control_point_amplitude(
                0.75,
                0.60,
                0.95,
                [0.60, 0.70, 0.80, 0.95],
                [0.00, 0.02, 0.04, 0.01],
            ),
            0.03,
        )

    def test_control_point_outside_region_is_zero(self):
        self.assertEqual(
            control_point_amplitude(
                0.50, 0.60, 0.95, [0.60, 0.75, 0.95], [0.01, 0.02, 0.03]
            ),
            0.0,
        )

    def test_control_point_metrics(self):
        metrics = control_point_metrics(
            [0.60, 0.70, 0.80], [0.01, 0.03, 0.02]
        )
        self.assertAlmostEqual(metrics["max_amplitude"], 0.03)
        self.assertAlmostEqual(metrics["max_adjacent_delta"], 0.02)

    def test_control_point_metrics_with_boundary_zeros(self):
        metrics = control_point_metrics(
            [0.60, 0.70, 0.80],
            [0.01, 0.03, 0.02],
            include_boundary_zeros=True,
        )
        self.assertAlmostEqual(metrics["max_adjacent_delta"], 0.02)
        metrics = control_point_metrics(
            [0.60, 0.70, 0.80],
            [0.03, 0.031, 0.032],
            include_boundary_zeros=True,
        )
        self.assertAlmostEqual(metrics["max_adjacent_delta"], 0.032)

    def test_zero_outside_region(self):
        self.assertEqual(spanwise_amplitude(0.5, 0.6, 0.95, 0.02, "uniform"), 0.0)
        self.assertEqual(spanwise_amplitude(0.98, 0.6, 0.95, 0.02, "uniform"), 0.0)

    def test_uniform(self):
        self.assertAlmostEqual(spanwise_amplitude(0.7, 0.6, 0.95, 0.02, "uniform"), 0.02)

    def test_tip_increasing(self):
        self.assertAlmostEqual(spanwise_amplitude(0.6, 0.6, 0.95, 0.02, "tip_increasing"), 0.0)
        self.assertAlmostEqual(spanwise_amplitude(0.95, 0.6, 0.95, 0.02, "tip_increasing"), 0.02)

    def test_tip_decreasing(self):
        self.assertAlmostEqual(spanwise_amplitude(0.6, 0.6, 0.95, 0.02, "tip_decreasing"), 0.02)
        self.assertAlmostEqual(spanwise_amplitude(0.95, 0.6, 0.95, 0.02, "tip_decreasing"), 0.0)

    def test_bell(self):
        midpoint = 0.5 * (0.6 + 0.95)
        self.assertAlmostEqual(spanwise_amplitude(0.6, 0.6, 0.95, 0.02, "bell"), 0.0)
        self.assertAlmostEqual(spanwise_amplitude(midpoint, 0.6, 0.95, 0.02, "bell"), 0.02)
        self.assertAlmostEqual(spanwise_amplitude(0.95, 0.6, 0.95, 0.02, "bell"), 0.0)


if __name__ == "__main__":
    unittest.main()

