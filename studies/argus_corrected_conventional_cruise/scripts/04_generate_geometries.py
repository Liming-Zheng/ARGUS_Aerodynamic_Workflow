"""Generate independent .vsp3 files for conventional hinged-control cases."""

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
    parser.add_argument("--designs", type=Path)
    parser.add_argument("--batch", type=int, default=1)
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
    from argus_conventional_control.geometry import apply_segmented_hinged_ailerons
    from argus_conventional_control.vspaero import write_csv

    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    design_path = args.designs or (
        project / "outputs" / "designs" / f"batch_{args.batch:02d}_designs.json"
    )
    cases = json.loads(design_path.read_text(encoding="utf-8"))
    output = project / "outputs" / "cases" / f"batch_{args.batch:02d}"
    output.mkdir(parents=True, exist_ok=True)
    settings = config["conventional_control"]
    vsp = load_vsp(Path(config["runtime"]["openvsp_root"]))
    manifest = []
    for case in cases:
        case_dir = output / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(config["source_model"])
        wing_id = vsp.FindGeom(config["wing_name"], 0)
        if not wing_id:
            raise RuntimeError(f"Wing not found: {config['wing_name']}")
        section_rows = apply_segmented_hinged_ailerons(
            vsp,
            wing_id,
            settings["segments"],
            case["segment_deflections_deg"],
            float(settings["hinge_x_over_c"]),
        )
        vsp.Update()
        model = case_dir / f"{case['case_id']}.vsp3"
        vsp.SetVSP3FileName(str(model))
        vsp.WriteVSPFile(str(model), vsp.SET_ALL)
        design = {
            **case,
            "baseline_model": config["source_model"],
            "generated_model": str(model),
            "hinge_x_over_c": settings["hinge_x_over_c"],
            "segments": settings["segments"],
        }
        (case_dir / f"{case['case_id']}_design.json").write_text(
            json.dumps(design, indent=2) + "\n", encoding="utf-8"
        )
        write_csv(case_dir / f"{case['case_id']}_section_schedule.csv", section_rows)
        manifest.append(
            {
                "case_id": case["case_id"],
                "batch": case["batch"],
                "inboard_deflection_deg": case["segment_deflections_deg"][0],
                "outboard_deflection_deg": case["segment_deflections_deg"][1],
                "segment_jump_deg": case["segment_jump_deg"],
                "model": str(model),
            }
        )
        print(f"Generated {case['case_id']}")
    write_csv(output / "case_manifest.csv", manifest)


if __name__ == "__main__":
    main()

