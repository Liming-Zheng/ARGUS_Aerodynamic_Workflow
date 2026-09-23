from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
CONTROL_ETAS = [0.68, 0.76, 0.84, 0.92, 1.0]
LOWER_TWIST_DEG = -1.0
UPPER_TWIST_DEG = 4.0
MAX_ADJACENT_DEG = 2.5


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--seed", type=int, default=20260729)
    return parser.parse_args()


def adjacent_deltas(values):
    return np.abs(np.diff(np.concatenate(([0.0], np.asarray(values, dtype=float)))))


def valid(values):
    values = np.asarray(values, dtype=float)
    return (
        np.min(values) >= LOWER_TWIST_DEG
        and np.max(values) <= UPPER_TWIST_DEG
        and np.max(adjacent_deltas(values)) <= MAX_ADJACENT_DEG
    )


def append_unique(collection, values, minimum_distance=0.25):
    vector = np.asarray(values, dtype=float)
    if not valid(vector):
        return
    if any(np.linalg.norm(vector - previous) < minimum_distance for previous in collection):
        return
    collection.append(vector)


def main():
    args = parse_args()
    project = args.project.resolve()
    output_root = project / "outputs" / "corrected_twist_optimization"
    output_root.mkdir(parents=True, exist_ok=True)
    samples = []

    deterministic = [
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [1.0, 1.5, 2.0, 2.0, 2.0],
        [1.5, 2.0, 2.5, 2.5, 2.0],
        [2.0, 2.5, 3.0, 2.5, 2.0],
        [2.5, 3.0, 3.0, 2.5, 1.5],
        [1.0, 2.0, 3.0, 3.5, 3.5],
        [0.5, 1.5, 2.5, 3.5, 4.0],
        [2.0, 3.0, 3.5, 2.5, 1.0],
        [-0.5, 0.5, 1.5, 2.5, 3.0],
        [-0.5, -0.5, -0.5, -0.5, -0.5],
        [0.0, 1.0, 2.0, 1.0, 0.0],
        [1.5, 2.5, 2.0, 1.0, 0.0],
    ]
    for values in deterministic:
        append_unique(samples, values, minimum_distance=0.0)

    rng = np.random.default_rng(args.seed)
    while len(samples) < args.count:
        trial = rng.uniform(LOWER_TWIST_DEG, UPPER_TWIST_DEG, size=5)
        append_unique(samples, trial)

    designs = []
    for index, vector in enumerate(samples[: args.count], start=1):
        values = vector.tolist()
        designs.append(
            {
                "case_id": f"ctw_seed_{index:03d}",
                "iteration": 0,
                "eta_start": 0.6,
                "eta_end": 1.0,
                "rotation_axis_x_over_c": 0.25,
                "shape_type": "distributed_section_twist",
                "control_etas": CONTROL_ETAS,
                "control_twist_deg": values,
                "max_adjacent_twist_delta_deg": float(np.max(adjacent_deltas(values))),
                "max_abs_twist_deg": max(abs(value) for value in values),
                "alpha_deg": 2.0,
                "mach": 0.1,
                "notes": "Corrected-airfoil distributed-twist optimization seed.",
            }
        )

    seed_path = project / "config" / "corrected_twist_seed_cases.json"
    seed_path.write_text(json.dumps(designs, indent=2) + "\n", encoding="utf-8")

    solver_config = {
        "control_etas": CONTROL_ETAS,
        "twist_bounds_deg": [LOWER_TWIST_DEG, UPPER_TWIST_DEG],
        "max_adjacent_twist_delta_deg": MAX_ADJACENT_DEG,
        "include_root_boundary_zero_in_adjacent_delta": True,
        "root_bending_increase_limit_percent": 6.8,
        "hinge_moment_constraint_enabled": False,
        "baseline_root_bending_moment_Nm": 110.75353915805569,
        "baseline_case": "baseline_corrected",
        "rotation_axis_x_over_c": 0.25,
        "cl_target": 0.428277635108,
        "geometry_status": "corrected_inserted_airfoil_interpolation",
    }
    solver_path = project / "config" / "corrected_twist_solver_config.json"
    solver_path.write_text(json.dumps(solver_config, indent=2) + "\n", encoding="utf-8")

    optimization_config = {
        "run_name": "corrected_twist_cdi",
        "case_prefix": "ctw",
        "sample_filter": {"case_id_prefixes": ["ctw_"]},
        "random_seed": args.seed,
        "paths": {
            "optimization_root": "outputs/corrected_twist_optimization",
            "baseline_model": (
                "../argus_morphing/outputs/tyler_validation_2026_07_29/"
                "baseline_corrected/baseline_corrected.vsp3"
            ),
            "solver_config": "config/corrected_twist_solver_config.json",
        },
        "design_variables": {
            "control_etas": CONTROL_ETAS,
            "twist_bounds_deg": [LOWER_TWIST_DEG, UPPER_TWIST_DEG],
            "max_adjacent_twist_delta_deg": MAX_ADJACENT_DEG,
            "include_root_boundary_zero_in_adjacent_delta": True,
            "rotation_axis_x_over_c": 0.25,
            "eta_start": 0.6,
            "eta_end": 1.0,
        },
        "objective": {
            "metric": "CDi",
            "direction": "minimize",
            "root_bending_weight": 0.0,
            "torque_weight": 0.0,
            "endpoint_weight": 0.0,
            "curvature_weight": 0.0,
        },
        "constraints": {
            "root_bending": {
                "enabled": True,
                "maximum_percent": 6.8,
                "penalty": 800.0,
            },
            "hinge_torque_proxy": {"enabled": False, "status": "not_applicable"},
        },
        "algorithm": {
            "name": "differential_evolution",
            "population_size": 12,
            "inner_max_iterations": 70,
            "tolerance": 1.0e-7,
            "polish": True,
            "random_search_samples": 100000,
            "minimum_candidate_distance": 0.25,
        },
        "surrogate": {"optimizer_restarts": 4, "exploration_weight": 0.15},
        "iterations": {
            "max_iterations": 2,
            "batch_size": 4,
            "minimum_absolute_improvement": 5.0e-7,
            "early_stop_patience": 2,
        },
        "runtime": {
            "workers": 4,
            "trim_mode": "fast",
            "fast_trim_alpha_low": 0.5,
            "fast_trim_alpha_high": 2.5,
            "fast_trim_alpha_points": 2,
            "search_cl_tolerance": 2.0e-4,
            "openvsp_python": "<OPENVSP_PYTHON>",
            "general_python": "python",
        },
        "notes": [
            "Independent twist optimization on the corrected inserted-airfoil baseline.",
            "Pure CDi objective with the same illustrative 6.8% root-bending screen.",
            "Five distributed-twist commands rotate sections about x/c=0.25.",
        ],
    }
    optimization_path = project / "config" / "optimization_corrected_twist_config.json"
    optimization_path.write_text(
        json.dumps(optimization_config, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(designs)} seeds to {seed_path}")
    print(f"Wrote solver config to {solver_path}")
    print(f"Wrote optimization config to {optimization_path}")


if __name__ == "__main__":
    main()


