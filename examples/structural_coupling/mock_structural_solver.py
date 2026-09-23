"""Minimal external structural solver for testing the ARGUS interface.

This is an interface demonstration only. Its proxy equations are not physical
models and must never be used for engineering conclusions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    request = json.loads(args.input.read_text(encoding="utf-8"))
    bending = abs(float(request["aerodynamics"]["half_wing_root_bending_n_m"]))
    variables = request["design"]["variables"]
    authority = max((abs(float(value)) for value in variables.values()), default=0.0)

    # Deliberately simple proxies used only to exercise the data contract.
    mass_kg = 10.0 + 20.0 * authority
    max_strain = 0.001 + 1.0e-6 * bending + 0.01 * authority
    actuator_force_n = 100.0 + 0.2 * bending
    strain_limit = max_strain / 0.005 - 1.0
    mass_limit = mass_kg / 40.0 - 1.0
    constraints = {
        "max_strain_ratio_minus_one": strain_limit,
        "mass_ratio_minus_one": mass_limit,
    }
    result = {
        "schema_version": "1.0",
        "case_id": request["design"]["case_id"],
        "operating_point": request["operating_point"]["name"],
        "feasible": all(value <= 0.0 for value in constraints.values()),
        "metrics": {
            "mass_kg": mass_kg,
            "max_stress_pa": 70.0e9 * max_strain,
            "max_strain": max_strain,
            "actuator_force_n": actuator_force_n,
            "actuator_stroke_m": 0.02 * authority,
        },
        "constraints": constraints,
        "files": {},
        "metadata": {
            "model": "non-physical interface demonstration",
            "constraint_convention": "g(x) <= 0 is feasible",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
