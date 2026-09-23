import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus_twist_morphing.load_metrics import (  # noqa: E402
    elliptic_distribution,
    elliptic_error,
    outer_lift_fraction,
    root_bending_moment,
    strip_outer_lift_fraction,
    strip_root_bending_moment,
    trapezoid,
)


class LoadMetricTests(unittest.TestCase):
    def test_trapezoid_linear(self):
        self.assertAlmostEqual(trapezoid([0.0, 0.5, 1.0], [0.0, 0.5, 1.0]), 0.5)

    def test_elliptic_reference_has_small_self_error(self):
        y = [i / 1000 for i in range(1001)]
        lift = elliptic_distribution(y, 1.0, 10.0)
        self.assertLess(elliptic_error(y, lift, 1.0), 1.0e-12)

    def test_root_bending_uniform_load(self):
        y = [i / 1000 for i in range(1001)]
        lift = [10.0] * len(y)
        self.assertAlmostEqual(root_bending_moment(y, lift), 5.0, places=5)

    def test_outer_fraction_uniform_load(self):
        y = [i / 1000 for i in range(1001)]
        self.assertAlmostEqual(
            outer_lift_fraction(y, y, [1.0] * len(y), 0.6),
            0.4,
            places=3,
        )

    def test_strip_metrics(self):
        y = [0.25, 0.75]
        widths = [0.5, 0.5]
        lift = [10.0, 10.0]
        self.assertAlmostEqual(strip_root_bending_moment(y, widths, lift), 5.0)
        self.assertAlmostEqual(strip_outer_lift_fraction(y, widths, lift, 0.6), 0.5)


if __name__ == "__main__":
    unittest.main()

