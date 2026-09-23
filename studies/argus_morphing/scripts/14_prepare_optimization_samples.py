from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import qmc


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_morphing.morphing_shapes import control_point_metrics  # noqa: E402


CONTROL_ETAS = [0.60, 0.6875, 0.775, 0.8625, 0.95]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--count", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260609)
    return parser.parse_args()


def case_id(index):
    return f"opt_s{index:03d}"


def anchors():
    return [
        [0.01] * 5,
        [0.02] * 5,
        [0.03] * 5,
        [0.04] * 5,
        [0.01, 0.015, 0.02, 0.025, 0.03],
        [0.03, 0.025, 0.02, 0.015, 0.01],
    ]


def main():
    args = parse_args()
    output = args.project / "outputs" / "optimization"
    output.mkdir(parents=True, exist_ok=True)
    amplitudes = anchors()
    sampler = qmc.LatinHypercube(d=len(CONTROL_ETAS), seed=args.seed)
    candidates = 0.04 * sampler.random(n=max(100, args.count * 20))
    for values in candidates:
        values = values.tolist()
        metrics = control_point_metrics(CONTROL_ETAS, values)
        if metrics["max_adjacent_delta"] > 0.02:
            continue
        if min(values) < 0.002:
            continue
        if any(np.linalg.norm(np.asarray(values) - np.asarray(old)) < 0.006 for old in amplitudes):
            continue
        amplitudes.append(values)
        if len(amplitudes) >= args.count:
            break
    if len(amplitudes) < args.count:
        raise RuntimeError(f"Only generated {len(amplitudes)} feasible samples")

    designs = []
    for index, values in enumerate(amplitudes[: args.count], start=1):
        metrics = control_point_metrics(CONTROL_ETAS, values)
        designs.append({
            "case_id": case_id(index),
            "eta_start": 0.60,
            "eta_end": 0.95,
            "x_h_over_c": 0.62,
            "A_max_over_c": max(values),
            "shape_type": "control_points",
            "control_etas": CONTROL_ETAS,
            "control_amplitudes_over_c": values,
            "max_adjacent_delta": metrics["max_adjacent_delta"],
            "max_spanwise_slope": metrics["max_spanwise_slope"],
            "alpha_deg": 2.0,
            "mach": 0.10,
            "notes": "ARGUS optimization initial design",
        })
    path = args.project / "config" / "optimization_initial_samples.json"
    path.write_text(json.dumps(designs, indent=2) + "\n", encoding="utf-8")
    config = {
        "control_etas": CONTROL_ETAS,
        "amplitude_bounds_over_c": [0.0, 0.04],
        "max_adjacent_delta": 0.02,
        "root_bending_increase_limit_percent": 7.0,
        "hinge_torque_proxy_limit_Nm": 1100.0,
        "x_h_over_c": 0.62,
        "cl_target": 0.428277635108,
        "initial_sample_count": len(designs),
        "seed": args.seed,
    }
    (args.project / "config" / "optimization_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(designs)} optimization samples to {path}")


if __name__ == "__main__":
    main()

