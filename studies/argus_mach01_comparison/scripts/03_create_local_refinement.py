"""Create deterministic local exact-search designs around the Mach 0.1 best."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np


PROJECT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def valid(values: np.ndarray, lower: float, upper: float, adjacent: float) -> bool:
    if np.any(values < lower) or np.any(values > upper):
        return False
    with_boundary = np.concatenate([[0.0], values])
    return bool(np.max(np.abs(np.diff(with_boundary))) <= adjacent + 1.0e-12)


def local_candidates(
    center: np.ndarray,
    *,
    lower: float,
    upper: float,
    adjacent: float,
    step: float,
    random_sigma: float,
    count: int,
    seed: int,
) -> list[np.ndarray]:
    candidates: list[np.ndarray] = []
    for axis in range(len(center)):
        for sign in (-1.0, 1.0):
            proposal = center.copy()
            proposal[axis] += sign * step
            if valid(proposal, lower, upper, adjacent):
                candidates.append(proposal)
    rng = np.random.default_rng(seed)
    attempts = 0
    while len(candidates) < count and attempts < 100000:
        attempts += 1
        proposal = center + rng.normal(0.0, random_sigma, size=len(center))
        if valid(proposal, lower, upper, adjacent):
            candidates.append(proposal)
    unique: list[np.ndarray] = []
    for proposal in candidates:
        if not any(np.linalg.norm(proposal - item) < 1.0e-10 for item in unique):
            unique.append(proposal)
        if len(unique) == count:
            break
    if len(unique) < count:
        raise RuntimeError(f"Generated only {len(unique)} local candidates")
    return unique


def main() -> None:
    config = json.loads(
        (PROJECT / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    cruise = Path(config["source_projects"]["cruise"])
    sys.path.insert(0, str(cruise / "src"))
    from argus_cruise_comparison.parameterization import schedule_from_iterables

    cruise_config = json.loads(
        (cruise / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    selected = {
        row["concept"]: row
        for row in read_csv(
            PROJECT / "plot" / "mach01_comparison" / "mach01_selected_summary.csv"
        )
    }
    settings = {
        "trailing_edge": {
            "bounds": cruise_config["morphing"]["trailing_edge"][
                "amplitude_bounds_over_c"
            ],
            "adjacent": cruise_config["morphing"]["trailing_edge"][
                "max_adjacent_control_delta_over_c"
            ],
            "step": 0.004,
            "sigma": 0.0035,
            "prefix": "m01_te",
            "units": "A_over_c",
        },
        "twist": {
            "bounds": cruise_config["morphing"]["twist"]["twist_bounds_deg"],
            "adjacent": cruise_config["morphing"]["twist"][
                "max_adjacent_control_delta_deg"
            ],
            "step": 0.5,
            "sigma": 0.4,
            "prefix": "m01_tw",
            "units": "deg",
        },
    }
    morph = cruise_config["morphing"]
    designs: list[dict] = []
    for concept_index, concept in enumerate(["trailing_edge", "twist"]):
        center = np.array(
            json.loads(selected[concept]["control_values_json"]),
            dtype=float,
        )
        setting = settings[concept]
        lower, upper = map(float, setting["bounds"])
        proposals = local_candidates(
            center,
            lower=lower,
            upper=upper,
            adjacent=float(setting["adjacent"]),
            step=float(setting["step"]),
            random_sigma=float(setting["sigma"]),
            count=20,
            seed=20260728 + concept_index,
        )
        for index, values in enumerate(proposals, start=1):
            case_id = f"{setting['prefix']}_r{index:02d}"
            schedule = schedule_from_iterables(
                morph["eta_start"],
                morph["eta_end"],
                morph["active_control_etas"],
                values.tolist(),
                morph["fixed_inboard_boundary_value"],
            )
            design = {
                "case_id": case_id,
                "concept": concept,
                "control_etas": morph["active_control_etas"],
                "control_values": values.tolist(),
                "seed_type": "mach01_local_exact_refinement",
                "parent_case_id": selected[concept]["case_id"],
                "schedule_metrics": schedule.metrics(
                    morph["dense_constraint_points"]
                ),
                "command_units": setting["units"],
            }
            if concept == "trailing_edge":
                design["x_h_over_c"] = morph["trailing_edge"]["x_h_over_c"]
            else:
                design["rotation_axis_x_over_c"] = morph["twist"][
                    "rotation_axis_x_over_c"
                ]
            designs.append(design)

    output = PROJECT / "outputs" / "refinement_designs"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "local_refinement_designs.json"
    path.write_text(json.dumps(designs, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(designs)} local exact-search designs to {path}")


if __name__ == "__main__":
    main()


