from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_cruise_comparison.vspaero import (
    aerodynamic_coefficients,
    collapse_spanwise_loads,
    integrate_load_metrics,
    interpolate_alpha,
)


class FakeVspResults:
    def __init__(self):
        self.values = {
            "CLtot": [0.42],
            "CDtot": [0.016],
            "CDi": [0.0098],
            "CDiw": [0.0057],
            "E": [0.55],
            "Ew": [0.95],
            "CMytot": [-0.10],
        }

    def GetDoubleResults(self, _result_id, name):
        return self.values.get(name, [])


class VspaeroHelperTests(unittest.TestCase):
    def test_near_and_far_field_coefficients_are_distinct(self):
        result = aerodynamic_coefficients(FakeVspResults(), "history")
        self.assertEqual(result["CDi"], result["CDi_near_field"])
        self.assertAlmostEqual(result["CDi_near_field"], 0.0098)
        self.assertAlmostEqual(result["CDiw_far_field"], 0.0057)
        self.assertAlmostEqual(result["E_near_field"], 0.55)
        self.assertAlmostEqual(result["Ew_far_field"], 0.95)

    def test_interpolate_alpha(self):
        alpha, slope = interpolate_alpha(
            [
                {"alpha_deg": 0.0, "CL": 0.1},
                {"alpha_deg": 4.0, "CL": 0.5},
            ],
            0.3,
        )
        self.assertAlmostEqual(alpha, 2.0)
        self.assertAlmostEqual(slope, 0.1)

    def test_aircraft_scale_load_integration(self):
        raw = [
            {
                "Yavg": 1.0,
                "dSpan": 0.5,
                "Chord": 1.0,
                "cl": 1.0,
                "cd": 0.1,
                "cdi": 0.05,
                "cmy": 0.0,
            }
        ]
        flight = {"dynamic_pressure_Pa": 100.0}
        scale = {"aircraft_m_per_model_unit": 2.0}
        native = {"reference_span_model_units": 4.0}
        strips = collapse_spanwise_loads(
            raw,
            flight,
            scale,
            native,
            morph_eta_start=0.4,
            morph_eta_end=1.0,
        )
        self.assertAlmostEqual(strips[0]["eta"], 0.5)
        self.assertAlmostEqual(strips[0]["lift_per_span_N_per_m"], 200.0)
        metrics = integrate_load_metrics(strips)
        self.assertAlmostEqual(metrics["half_wing_lift_N"], 200.0)
        self.assertAlmostEqual(
            metrics["half_wing_root_bending_moment_Nm"], 400.0
        )


if __name__ == "__main__":
    unittest.main()

