from __future__ import annotations

import json
from itertools import product
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def main():
    output_root = PROJECT / "outputs" / "corrected_low_speed"
    (output_root / "designs").mkdir(parents=True, exist_ok=True)

    levels = [-6.6544, -3.3272, 0.0, 3.3272, 6.6544]
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
    for index, values in enumerate(product(levels, repeat=2), start=1):
        cases.append(
            {
                "case_id": f"chc_g01_c{index:02d}",
                "concept": "conventional_hinged",
                "batch": 1,
                "seed_type": "corrected_exact_coarse_grid",
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
    design_path = output_root / "designs" / "batch_01_designs.json"
    design_path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")

    solver = {
        "cl_target": 0.428277635108,
        "baseline_case": "baseline_corrected",
        "baseline_CDi": 0.009878741611,
        "baseline_root_bending_moment_Nm": 110.75353915805569,
        "root_bending_increase_limit_percent": 6.8,
        "deflection_bounds_deg": [-6.6544, 6.6544],
        "hinge_moment_constraint_enabled": False,
        "geometry_status": "corrected_inserted_airfoil_interpolation",
        "control_geometry": {
            "source": "NASA TP-1580 Figure 1(b), AR=12 low-speed aileron",
            "hinge_x_over_c": 0.70,
            "segments": segments,
            "representation": "zero-gap rigid aft-section rotation",
        },
    }
    solver_path = PROJECT / "config" / "corrected_low_speed_solver_config.json"
    solver_path.write_text(json.dumps(solver, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} coarse cases to {design_path}")
    print(f"Wrote solver config to {solver_path}")


if __name__ == "__main__":
    main()

