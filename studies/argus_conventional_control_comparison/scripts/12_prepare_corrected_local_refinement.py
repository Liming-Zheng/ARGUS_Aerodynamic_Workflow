from __future__ import annotations

import csv
import json
from itertools import product
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main():
    root = PROJECT / "outputs" / "corrected_low_speed"
    samples = rows(root / "optimization_samples.csv")
    feasible = [row for row in samples if row["feasible"].lower() == "true"]
    if not feasible:
        raise RuntimeError("The coarse grid contains no feasible candidates")
    best = min(feasible, key=lambda row: float(row["CDi"]))
    center = [
        float(best["delta_inboard_deg"]),
        float(best["delta_outboard_deg"]),
    ]
    lower, upper = [-6.6544, 6.6544]
    half_width = 1.6636
    offsets = [-half_width, -0.5 * half_width, 0.0, 0.5 * half_width, half_width]
    levels = [
        [max(lower, min(upper, value + offset)) for offset in offsets]
        for value in center
    ]
    coarse_keys = {
        (
            round(float(row["delta_inboard_deg"]), 6),
            round(float(row["delta_outboard_deg"]), 6),
        )
        for row in samples
    }
    segments = [
        {
            "name": "low_speed_aileron_inboard",
            "eta_start": 0.710,
            "eta_end": 0.852,
        },
        {
            "name": "low_speed_aileron_outboard",
            "eta_start": 0.852,
            "eta_end": 0.970,
        },
    ]
    cases = []
    seen = set()
    for values in product(*levels):
        key = tuple(round(value, 6) for value in values)
        if key in coarse_keys or key in seen:
            continue
        seen.add(key)
        cases.append(
            {
                "case_id": f"chc_g02_c{len(cases) + 1:02d}",
                "concept": "conventional_hinged",
                "batch": 2,
                "seed_type": "corrected_exact_local_grid",
                "parent_case": best["case_id"],
                "eta_start": 0.710,
                "eta_end": 0.970,
                "hinge_x_over_c": 0.70,
                "segments": segments,
                "segment_deflections_deg": list(values),
                "max_abs_deflection_deg": max(abs(value) for value in values),
                "segment_jump_deg": abs(values[1] - values[0]),
                "mach": 0.1,
            }
        )
    path = root / "designs" / "batch_02_designs.json"
    path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(
        f"Coarse best={best['case_id']} at {center}; "
        f"wrote {len(cases)} local cases to {path}"
    )


if __name__ == "__main__":
    main()

