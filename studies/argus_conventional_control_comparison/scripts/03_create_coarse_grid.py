"""Create the exact two-segment coarse-grid optimization cases."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    levels = [float(value) for value in config["optimization"]["coarse_grid_levels_deg"]]
    cases = []
    for index, values in enumerate(product(levels, repeat=2), start=1):
        cases.append(
            {
                "case_id": f"conv_g01_c{index:02d}",
                "concept": "conventional_hinged",
                "batch": 1,
                "seed_type": "exact_coarse_grid",
                "segment_deflections_deg": list(values),
                "max_abs_deflection_deg": max(abs(value) for value in values),
                "segment_jump_deg": abs(values[1] - values[0]),
            }
        )
    output = project / "outputs" / "designs"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "batch_01_designs.json"
    path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} coarse-grid cases to {path}")


if __name__ == "__main__":
    main()

