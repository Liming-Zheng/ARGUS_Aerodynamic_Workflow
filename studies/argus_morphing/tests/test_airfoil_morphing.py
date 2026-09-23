import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus_morphing.airfoil_morphing import (  # noqa: E402
    camber_displacement,
    morph_airfoil,
    validate_morphed_airfoil,
)


class AirfoilMorphingTests(unittest.TestCase):
    def setUp(self):
        self.x = np.linspace(0.0, 1.0, 201)
        thickness = 0.12 * np.sin(np.pi * self.x)
        self.upper = 0.5 * thickness
        self.lower = -0.5 * thickness

    def test_displacement_boundary_conditions(self):
        displacement = camber_displacement(self.x, 0.5, 0.02)
        self.assertTrue(np.allclose(displacement[self.x < 0.5], 0.0))
        self.assertAlmostEqual(displacement[-1], -0.02)
        slope = np.gradient(displacement, self.x)
        self.assertLess(abs(slope[np.argmin(abs(self.x - 0.5))]), 1.0e-3)

    def test_positive_amplitude_moves_te_down(self):
        result = morph_airfoil(self.x, self.upper, self.lower, 0.5, 0.02)
        self.assertAlmostEqual(result.displacement[-1], -0.02)

    def test_thickness_is_preserved(self):
        result = morph_airfoil(self.x, self.upper, self.lower, 0.35, -0.04)
        before = self.upper - self.lower
        after = result.upper_z - result.lower_z
        self.assertTrue(np.allclose(before, after))

    def test_validation_accepts_regular_case(self):
        result = morph_airfoil(self.x, self.upper, self.lower, 0.62, 0.02)
        checks = validate_morphed_airfoil(result, 0.62)
        self.assertTrue(checks["valid"])


if __name__ == "__main__":
    unittest.main()


