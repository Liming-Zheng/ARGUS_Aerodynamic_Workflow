import importlib.util
import math
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "15_run_optimization_samples.py"
SPEC = importlib.util.spec_from_file_location("run_optimization_samples", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OptimizationSampleUnitTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "native_length_to_m": 0.3048,
            "reference_span_native": 12.0,
            "load_condition_rho_kg_m3": 1.225,
            "load_condition_velocity_m_s": 30.48,
            "legacy_rho_kg_m3": 1.225,
            "legacy_velocity_m_s": 45.0,
        }
        self.design = {
            "eta_start": 0.6,
            "eta_end": 1.0,
            "x_h_over_c": 0.62,
        }

    def test_native_feet_are_converted_before_dimensional_loads(self):
        raw = [{
            "Yavg": 3.0,
            "dSpan": 1.0,
            "Chord": 2.0,
            "cl": 0.5,
            "cd": 0.02,
            "cdi": 0.01,
            "cmy": -0.1,
        }]
        row = MODULE.collapse_spanwise_loads(
            raw, self.design, self.config
        )[0]
        q = 0.5 * 1.225 * 30.48**2
        self.assertAlmostEqual(row["y_m"], 3.0 * 0.3048)
        self.assertAlmostEqual(row["dy_m"], 0.3048)
        self.assertAlmostEqual(row["chord_m"], 2.0 * 0.3048)
        self.assertAlmostEqual(
            row["lift_per_span_N_per_m"],
            q * 2.0 * 0.3048 * 0.5,
        )
        self.assertNotIn("hinge_moment_proxy_Nm_per_m", row)

    def test_legacy_moment_scale_contains_q_and_length_cubed(self):
        expected = (
            (30.48 / 45.0) ** 2
            * 0.3048**3
        )
        self.assertTrue(math.isclose(
            MODULE.legacy_to_audited_moment_scale(self.config),
            expected,
            rel_tol=1.0e-12,
        ))


if __name__ == "__main__":
    unittest.main()

