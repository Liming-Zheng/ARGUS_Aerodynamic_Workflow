from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    return parser.parse_args()


def case_id(x_h, amplitude, shape):
    xh = f"{x_h:.2f}".replace(".", "p")
    amp = f"{amplitude:+.2f}".replace("+", "p").replace("-", "m").replace(".", "p")
    return f"doe_xh_{xh}_A_{amp}_{shape}"


def main():
    args = parse_args()
    x_h_values = [0.35, 0.50, 0.62]
    amplitudes = [-0.04, -0.02, -0.01, 0.00, 0.01, 0.02, 0.04]
    shapes = ["uniform", "tip_increasing", "tip_decreasing", "bell"]
    cases = []
    for x_h, amplitude, shape in itertools.product(x_h_values, amplitudes, shapes):
        cases.append({
            "case_id": case_id(x_h, amplitude, shape),
            "eta_start": 0.60,
            "eta_end": 0.95,
            "x_h_over_c": x_h,
            "A_max_over_c": amplitude,
            "shape_type": shape,
            "alpha_deg": 2.0,
            "mach": 0.10,
            "notes": "Minimal DOE on refined wing-only baseline",
        })
    output = args.project / "config" / "minimal_doe_cases.json"
    output.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} DOE definitions to {output}")


if __name__ == "__main__":
    main()

