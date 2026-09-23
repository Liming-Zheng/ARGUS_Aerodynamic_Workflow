from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_morphing.morphing_shapes import control_point_metrics  # noqa: E402


CONTROL_ETAS = [0.6, 0.7, 0.8, 0.9, 1.0]
MCV2 = np.asarray(
    [
        0.00802664819714527,
        0.02597787349928656,
        0.03496782672156966,
        0.018198741897711118,
        0.0002180441893945284,
    ]
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--seed", type=int, default=20260729)
    return parser.parse_args()


def valid(values):
    metrics = control_point_metrics(
        CONTROL_ETAS,
        values,
        include_boundary_zeros=True,
    )
    return (
        min(values) >= 0.0
        and max(values) <= 0.035
        and metrics["max_adjacent_delta"] <= 0.018
    )


def append_unique(collection, values, minimum_distance=0.003):
    vector = np.asarray(values, dtype=float)
    if not valid(vector):
        return
    if any(np.linalg.norm(vector - previous) < minimum_distance for previous in collection):
        return
    collection.append(vector)


def main():
    args = parse_args()
    project = args.project.resolve()
    output_root = project / "outputs" / "corrected_te_optimization"
    output_root.mkdir(parents=True, exist_ok=True)
    samples = []

    append_unique(samples, np.zeros(5), minimum_distance=0.0)
    for scale in [0.40, 0.55, 0.70, 0.82, 0.90, 0.95]:
        append_unique(samples, scale * MCV2)
    for peak in [0.012, 0.020, 0.028, 0.034]:
        append_unique(samples, [0.25 * peak, 0.75 * peak, peak, 0.65 * peak, 0.15 * peak])
    for level in [0.008, 0.014]:
        append_unique(samples, [level, level, level, level, level])

    rng = np.random.default_rng(args.seed)
    while len(samples) < args.count:
        trial = rng.uniform(0.0, 0.035, size=5)
        append_unique(samples, trial)

    designs = []
    for index, vector in enumerate(samples[: args.count], start=1):
        values = vector.tolist()
        metrics = control_point_metrics(
            CONTROL_ETAS,
            values,
            include_boundary_zeros=True,
        )
        designs.append(
            {
                "case_id": f"cte_seed_{index:03d}",
                "iteration": 0,
                "eta_start": 0.6,
                "eta_end": 1.0,
                "x_h_over_c": 0.62,
                "A_max_over_c": max(values),
                "shape_type": "control_points",
                "control_etas": CONTROL_ETAS,
                "control_amplitudes_over_c": values,
                "max_adjacent_delta": metrics["max_adjacent_delta"],
                "max_spanwise_slope": metrics["max_spanwise_slope"],
                "alpha_deg": 2.0,
                "mach": 0.1,
                "notes": "Corrected-airfoil trailing-edge optimization seed.",
            }
        )

    seed_path = project / "config" / "corrected_te_seed_cases.json"
    seed_path.write_text(json.dumps(designs, indent=2) + "\n", encoding="utf-8")

    solver_config = {
        "control_etas": CONTROL_ETAS,
        "amplitude_bounds_over_c": [0.0, 0.035],
        "max_adjacent_delta": 0.018,
        "include_boundary_zeros_in_adjacent_delta": True,
        "root_bending_increase_limit_percent": 6.8,
        "hinge_moment_constraint_enabled": False,
        "baseline_root_bending_moment_Nm": 110.75353915805569,
        "baseline_case": "baseline_corrected",
        "x_h_over_c": 0.62,
        "cl_target": 0.428277635108,
        "geometry_status": "corrected_inserted_airfoil_interpolation",
    }
    solver_path = project / "config" / "corrected_te_solver_config.json"
    solver_path.write_text(
        json.dumps(solver_config, indent=2) + "\n",
        encoding="utf-8",
    )

    user_config = {
        "run_name": "corrected_te_cdi",
        "case_prefix": "cte",
        "sample_filter": {"case_id_prefixes": ["cte_"]},
        "random_seed": args.seed,
        "paths": {
            "optimization_root": "outputs/corrected_te_optimization",
            "baseline_model": (
                "outputs/tyler_validation_2026_07_29/"
                "baseline_corrected/baseline_corrected.vsp3"
            ),
            "solver_config": "config/corrected_te_solver_config.json",
        },
        "design_variables": {
            "control_etas": CONTROL_ETAS,
            "amplitude_bounds_over_c": [0.0, 0.035],
            "max_adjacent_delta": 0.018,
            "include_boundary_zeros_in_adjacent_delta": True,
            "x_h_over_c": 0.62,
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
            "hinge_torque_proxy": {
                "enabled": False,
                "status": "withdrawn",
            },
        },
        "algorithm": {
            "name": "differential_evolution",
            "population_size": 12,
            "inner_max_iterations": 70,
            "tolerance": 1.0e-7,
            "polish": True,
            "random_search_samples": 100000,
            "minimum_candidate_distance": 0.003,
        },
        "surrogate": {
            "optimizer_restarts": 4,
            "exploration_weight": 0.15,
        },
        "iterations": {
            "max_iterations": 2,
            "batch_size": 4,
            "minimum_absolute_improvement": 5.0e-7,
            "early_stop_patience": 2,
        },
        "runtime": {
            "workers": 4,
            "trim_mode": "fast",
            "fast_trim_alpha_low": 0.8,
            "fast_trim_alpha_high": 2.2,
            "fast_trim_alpha_points": 2,
            "search_cl_tolerance": 2.0e-4,
            "openvsp_python": "<OPENVSP_PYTHON>",
            "general_python": "python",
        },
        "notes": [
            "Independent optimization on corrected inserted-airfoil baseline.",
            "Pure CDi objective with illustrative root-bending and smoothness screens.",
            "No hinge-moment constraint.",
        ],
    }
    user_path = project / "config" / "optimization_corrected_te_config.json"
    user_path.write_text(json.dumps(user_config, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(designs)} seeds to {seed_path}")
    print(f"Wrote solver config to {solver_path}")
    print(f"Wrote user config to {user_path}")


if __name__ == "__main__":
    main()


