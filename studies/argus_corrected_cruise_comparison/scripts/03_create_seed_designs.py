"""Create a deterministic, smooth seed design set for both concepts."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--random-seeds-per-concept", type=int, default=8)
    return parser.parse_args()


def random_smooth_values(
    rng: random.Random,
    lower: float,
    upper: float,
    max_adjacent: float,
    count: int,
) -> list[float]:
    for _ in range(10000):
        values = [
            rng.uniform(
                max(lower, -max_adjacent),
                min(upper, max_adjacent),
            )
        ]
        for _ in range(1, count):
            local_lower = max(lower, values[-1] - max_adjacent)
            local_upper = min(upper, values[-1] + max_adjacent)
            values.append(rng.uniform(local_lower, local_upper))
        if max(abs(value) for value in values) >= 0.25 * max(abs(lower), upper):
            return values
    raise RuntimeError("Could not generate a nontrivial smooth seed")


def scaled(shape: list[float], magnitude: float) -> list[float]:
    peak = max(abs(value) for value in shape)
    return [magnitude * value / peak for value in shape]


def concept_cases(
    concept: str,
    lower: float,
    upper: float,
    max_adjacent: float,
    control_etas: list[float],
    random_count: int,
    rng: random.Random,
) -> list[dict]:
    magnitude = 0.65 * max(abs(lower), abs(upper))
    templates = [
        [1, 1, 1, 1, 1],
        [-1, -1, -1, -1, -1],
        [0.2, 0.4, 0.6, 0.8, 1.0],
        [-0.2, -0.4, -0.6, -0.8, -1.0],
        [0.2, 0.8, 1.0, 0.8, 0.4],
        [-0.6, -0.3, 0.0, 0.3, 0.6],
    ]
    cases: list[dict] = []
    for index, template in enumerate(templates, start=1):
        values = scaled(template, magnitude)
        cases.append(
            {
                "case_id": f"{concept}_seed_h{index:02d}",
                "concept": concept,
                "control_etas": control_etas,
                "control_values": values,
                "seed_type": "handcrafted",
            }
        )
    for index in range(1, random_count + 1):
        values = random_smooth_values(
            rng, lower, upper, max_adjacent, len(control_etas)
        )
        cases.append(
            {
                "case_id": f"{concept}_seed_r{index:02d}",
                "concept": concept,
                "control_etas": control_etas,
                "control_values": values,
                "seed_type": "random_smooth",
            }
        )
    return cases


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    sys.path.insert(0, str(project / "src"))
    from argus_cruise_comparison.parameterization import schedule_from_iterables

    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    morph = config["morphing"]
    control_etas = [float(value) for value in morph["active_control_etas"]]
    rng = random.Random(20260724)
    te = morph["trailing_edge"]
    twist = morph["twist"]
    cases = concept_cases(
        "trailing_edge",
        *te["amplitude_bounds_over_c"],
        te["max_adjacent_control_delta_over_c"],
        control_etas,
        args.random_seeds_per_concept,
        rng,
    )
    cases.extend(
        concept_cases(
            "twist",
            *twist["twist_bounds_deg"],
            twist["max_adjacent_control_delta_deg"],
            control_etas,
            args.random_seeds_per_concept,
            rng,
        )
    )
    for case in cases:
        schedule = schedule_from_iterables(
            morph["eta_start"],
            morph["eta_end"],
            case["control_etas"],
            case["control_values"],
            morph["fixed_inboard_boundary_value"],
        )
        case["schedule_metrics"] = schedule.metrics(
            morph["dense_constraint_points"]
        )
        if case["concept"] == "trailing_edge":
            case["x_h_over_c"] = te["x_h_over_c"]
            case["command_units"] = "A_over_c"
        else:
            case["rotation_axis_x_over_c"] = twist[
                "rotation_axis_x_over_c"
            ]
            case["command_units"] = "deg"

    output = project / "outputs" / "seed_designs"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "seed_designs.json"
    path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(cases)} designs "
        f"({sum(c['concept'] == 'trailing_edge' for c in cases)} TE, "
        f"{sum(c['concept'] == 'twist' for c in cases)} twist): {path}"
    )


if __name__ == "__main__":
    main()

