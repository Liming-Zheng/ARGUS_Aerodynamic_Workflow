import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus_morphing.optimization_framework import (  # noqa: E402
    exact_objective,
    filtered_exact_samples,
    is_feasible,
    objective_definition,
    validate_user_config,
)


def config():
    return {
        "random_seed": 1,
        "design_variables": {
            "control_etas": [0.6, 0.7],
            "amplitude_bounds_over_c": [0.0, 0.04],
            "max_adjacent_delta": 0.02,
        },
        "objective": {
            "metric": "CDi",
            "direction": "minimize",
            "root_bending_weight": 0.0,
            "torque_weight": 0.0,
        },
        "constraints": {
            "root_bending": {"enabled": True, "maximum_percent": 7.0},
            "hinge_torque_proxy": {"enabled": True, "maximum_abs_Nm": 1100.0},
        },
        "algorithm": {"name": "random_search"},
        "iterations": {"max_iterations": 2, "batch_size": 1},
    }


class OptimizationFrameworkTests(unittest.TestCase):
    def test_validate_config(self):
        validate_user_config(config())

    def test_exact_objective(self):
        row = {
            "CDi": 0.009,
            "root_bending_increase_percent": 5.0,
            "hinge_torque_proxy_Nm": -900.0,
        }
        self.assertAlmostEqual(
            exact_objective(row, objective_definition(config())),
            0.009,
        )

    def test_feasibility(self):
        row = {
            "A1_over_c": 0.005,
            "A2_over_c": 0.015,
            "root_bending_increase_percent": 6.5,
            "hinge_torque_proxy_Nm": -1000.0,
            "max_adjacent_delta": 0.01,
        }
        self.assertTrue(is_feasible(row, config()))
        row["root_bending_increase_percent"] = 7.1
        self.assertFalse(is_feasible(row, config()))

    def test_disabled_hinge_constraint_does_not_require_legacy_proxy(self):
        cfg = config()
        cfg["constraints"]["hinge_torque_proxy"]["enabled"] = False
        row = {
            "A1_over_c": 0.005,
            "A2_over_c": 0.015,
            "CDi": 0.0089,
            "root_bending_increase_percent": 6.5,
            "max_adjacent_delta": 0.01,
        }
        self.assertTrue(is_feasible(row, cfg))
        self.assertAlmostEqual(
            exact_objective(row, objective_definition(cfg)),
            row["CDi"],
        )

    def test_boundary_zero_adjacent_delta_feasibility(self):
        cfg = config()
        cfg["design_variables"]["include_boundary_zeros_in_adjacent_delta"] = True
        row = {
            "A1_over_c": 0.03,
            "A2_over_c": 0.031,
            "root_bending_increase_percent": 6.5,
            "hinge_torque_proxy_Nm": -1000.0,
            "max_adjacent_delta": 0.001,
        }
        self.assertFalse(is_feasible(row, cfg))

    def test_filtered_exact_samples_by_case_prefix(self):
        cfg = config()
        cfg["sample_filter"] = {"case_id_prefixes": ["wsc_", "wsu_"]}
        rows = [
            {"case_id": "mbr_c01_l011"},
            {"case_id": "wsc_s001"},
            {"case_id": "wsu_i001_c01"},
        ]
        self.assertEqual(
            [row["case_id"] for row in filtered_exact_samples(rows, cfg)],
            ["wsc_s001", "wsu_i001_c01"],
        )


if __name__ == "__main__":
    unittest.main()

