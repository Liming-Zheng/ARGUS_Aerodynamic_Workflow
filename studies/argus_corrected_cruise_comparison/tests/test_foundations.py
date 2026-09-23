from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_cruise_comparison.atmosphere import flight_state, isa_state
from argus_cruise_comparison.constraints import constraint_status
from argus_cruise_comparison.geometry import trailing_edge_offset
from argus_cruise_comparison.parameterization import MorphingSchedule
from argus_cruise_comparison.scaling import build_scale_definition


class AtmosphereTests(unittest.TestCase):
    def test_standard_atmosphere_at_cruise_altitudes(self):
        ten = isa_state(10000.0)
        twelve = isa_state(12000.0)
        self.assertAlmostEqual(ten.density_kg_m3, 0.412706, places=5)
        self.assertAlmostEqual(twelve.density_kg_m3, 0.310828, places=5)

    def test_target_cl_uses_lift_not_mass_or_cl_schedule(self):
        early = flight_state("early", 10000.0, 0.78, 74500.0, 122.6)
        late = flight_state("late", 12000.0, 0.78, 56000.0, 122.6)
        self.assertAlmostEqual(early["target_CL"], 0.529297, places=5)
        self.assertAlmostEqual(late["target_CL"], 0.544114, places=5)
        self.assertLess(late["target_lift_N"], early["target_lift_N"])


class ScalingTests(unittest.TestCase):
    def test_area_scale_preserves_reference_aspect_ratio(self):
        config = json.loads(
            (PROJECT / "config" / "study_config.json").read_text(encoding="utf-8")
        )
        scale = build_scale_definition(config)
        self.assertAlmostEqual(scale["aircraft_reference_area_m2"], 122.6)
        self.assertAlmostEqual(scale["aircraft_reference_aspect_ratio"], 12.0)
        self.assertAlmostEqual(scale["aircraft_reference_span_m"], 38.356225, places=5)


class ParameterizationTests(unittest.TestCase):
    def setUp(self):
        self.schedule = MorphingSchedule(
            eta_start=0.6,
            eta_end=1.0,
            active_control_etas=(0.68, 0.76, 0.84, 0.92, 1.0),
            active_values=(0.01, 0.02, 0.018, 0.012, 0.008),
        )

    def test_inboard_boundary_is_zero_and_tip_is_free(self):
        self.assertEqual(self.schedule.value(0.6), 0.0)
        self.assertEqual(self.schedule.value(0.5), 0.0)
        self.assertAlmostEqual(self.schedule.value(1.0), 0.008)

    def test_pchip_does_not_overshoot_control_envelope(self):
        values = [value for _, value in self.schedule.sample()]
        self.assertGreaterEqual(min(values), 0.0)
        self.assertLessEqual(max(values), 0.02 + 1.0e-12)

    def test_adjacent_metric_has_no_virtual_zero_after_tip(self):
        metrics = self.schedule.metrics()
        self.assertAlmostEqual(metrics["max_adjacent_control_delta"], 0.01)
        self.assertAlmostEqual(metrics["tip_value"], 0.008)

    def test_trailing_edge_offset_is_position_continuous(self):
        self.assertEqual(trailing_edge_offset(0.5, 0.62, 0.02), 0.0)
        self.assertEqual(trailing_edge_offset(0.62, 0.62, 0.02), 0.0)
        self.assertAlmostEqual(
            trailing_edge_offset(1.0, 0.62, 0.02), -0.02
        )


class ConstraintTests(unittest.TestCase):
    def test_inactive_moment_constraint_is_not_evaluated(self):
        status = constraint_status(
            root_bending_moment_Nm=100.0,
            root_bending_limit_Nm=100.0,
            max_abs_command=0.02,
            max_abs_command_limit=0.035,
            max_adjacent_delta=0.01,
            max_adjacent_delta_limit=0.018,
        )
        self.assertTrue(status["feasible"])
        self.assertEqual(status["active_constraints"], ["absolute_root_bending"])
        self.assertEqual(len(status["constraints"]), 3)

    def test_small_penalty_overshoot_uses_explicit_tolerance(self):
        status = constraint_status(
            root_bending_moment_Nm=100.05,
            root_bending_limit_Nm=100.0,
            max_abs_command=0.02,
            max_abs_command_limit=0.035,
            max_adjacent_delta=0.01,
            max_adjacent_delta_limit=0.018,
            relative_tolerance=0.001,
        )
        self.assertTrue(status["feasible"])


if __name__ == "__main__":
    unittest.main()

