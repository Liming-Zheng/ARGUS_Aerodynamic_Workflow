"""Propose an exact local grid around the best coarse point in either state."""

from __future__ import annotations

import csv
import json
from itertools import product
from pathlib import Path


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def feasible(row: dict) -> bool:
    return row["feasible"].lower() == "true"


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    coarse = rows(project / "outputs" / "evaluations" / "batch_01_results.csv")
    half_width = float(config["optimization"]["refinement_half_width_deg"])
    lower, upper = [
        float(value)
        for value in config["conventional_control"]["optimization_deflection_bounds_deg"]
    ]
    centers = []
    for state in ["early_cruise", "late_cruise"]:
        candidates = [
            row for row in coarse
            if row["flight_state"] == state and feasible(row)
        ]
        best = min(candidates, key=lambda row: float(row["CDi"]))
        centers.append(
            (
                float(best["delta_inboard_deg"]),
                float(best["delta_outboard_deg"]),
                state,
                best["case_id"],
            )
        )
    unique = {}
    for center_in, center_out, state, source in centers:
        levels_in = [
            max(lower, center_in - half_width),
            center_in,
            min(upper, center_in + half_width),
        ]
        levels_out = [
            max(lower, center_out - half_width),
            center_out,
            min(upper, center_out + half_width),
        ]
        for values in product(levels_in, levels_out):
            key = tuple(round(value, 6) for value in values)
            unique.setdefault(key, {"states": [], "sources": []})
            unique[key]["states"].append(state)
            unique[key]["sources"].append(source)
    coarse_keys = {
        (round(float(row["delta_inboard_deg"]), 6), round(float(row["delta_outboard_deg"]), 6))
        for row in coarse
    }
    cases = []
    for values, reason in sorted(unique.items()):
        if values in coarse_keys:
            continue
        index = len(cases) + 1
        cases.append(
            {
                "case_id": f"conv_g02_c{index:02d}",
                "concept": "conventional_hinged",
                "batch": 2,
                "seed_type": "exact_local_refinement",
                "proposal_states": sorted(set(reason["states"])),
                "parent_cases": sorted(set(reason["sources"])),
                "segment_deflections_deg": list(values),
                "max_abs_deflection_deg": max(abs(value) for value in values),
                "segment_jump_deg": abs(values[1] - values[0]),
            }
        )
    path = project / "outputs" / "designs" / "batch_02_designs.json"
    path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} local-refinement cases to {path}")


if __name__ == "__main__":
    main()

