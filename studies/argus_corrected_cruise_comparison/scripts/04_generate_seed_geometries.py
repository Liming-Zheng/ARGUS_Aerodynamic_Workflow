"""Generate independent OpenVSP geometry files for all seed designs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output-root", type=Path)
    return parser.parse_args()


def load_vsp(openvsp_root: Path):
    os.add_dll_directory(str(openvsp_root))
    os.add_dll_directory(str(openvsp_root / "python" / "openvsp" / "openvsp"))
    for relative in [
        "python/openvsp",
        "python/openvsp_config",
        "python/degen_geom",
        "python/utilities",
    ]:
        sys.path.insert(0, str(openvsp_root / relative))
    import openvsp as vsp

    return vsp


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    sys.path.insert(0, str(project / "src"))
    from argus_cruise_comparison.geometry import (
        apply_trailing_edge_morphing,
        apply_twist_morphing,
    )
    from argus_cruise_comparison.parameterization import schedule_from_iterables
    from argus_cruise_comparison.vspaero import write_csv

    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    cases_path = (
        args.cases
        if args.cases is not None
        else project / "outputs" / "seed_designs" / "seed_designs.json"
    )
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    output_root = (
        args.output_root.resolve()
        if args.output_root is not None
        else project / "outputs" / "seed_cases"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    vsp = load_vsp(Path(config["runtime"]["openvsp_root"]))
    morph = config["morphing"]
    manifest: list[dict] = []

    for case in cases:
        case_dir = output_root / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(config["source_model"])
        wing_id = vsp.FindGeom(config["wing_name"], 0)
        if not wing_id:
            raise RuntimeError(f"Wing geometry not found: {config['wing_name']}")
        schedule = schedule_from_iterables(
            morph["eta_start"],
            morph["eta_end"],
            case["control_etas"],
            case["control_values"],
            morph["fixed_inboard_boundary_value"],
        )
        if case["concept"] == "trailing_edge":
            section_rows = apply_trailing_edge_morphing(
                vsp, wing_id, schedule, case["x_h_over_c"]
            )
        elif case["concept"] == "twist":
            section_rows = apply_twist_morphing(
                vsp,
                wing_id,
                schedule,
                case["rotation_axis_x_over_c"],
            )
        else:
            raise ValueError(f"Unknown morphing concept: {case['concept']}")

        vsp.Update()
        model = case_dir / f"{case['case_id']}.vsp3"
        vsp.SetVSP3FileName(str(model))
        vsp.WriteVSPFile(str(model), vsp.SET_ALL)
        design_path = case_dir / f"{case['case_id']}_design.json"
        design_path.write_text(
            json.dumps(
                {
                    **case,
                    "baseline_model": config["source_model"],
                    "generated_model": str(model),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        write_csv(
            case_dir / f"{case['case_id']}_section_schedule.csv",
            section_rows,
        )
        manifest.append(
            {
                "case_id": case["case_id"],
                "concept": case["concept"],
                "seed_type": case.get("seed_type", "optimization_candidate"),
                "tip_value": case["schedule_metrics"]["tip_value"],
                "max_abs_value_dense": case["schedule_metrics"][
                    "max_abs_value_dense"
                ],
                "max_adjacent_control_delta": case["schedule_metrics"][
                    "max_adjacent_control_delta"
                ],
                "morphed_geometric_sections": sum(
                    bool(row["morphed"]) for row in section_rows
                ),
                "model": str(model),
            }
        )
        print(f"Generated {case['case_id']}")
    write_csv(output_root / "case_manifest.csv", manifest)


if __name__ == "__main__":
    main()

