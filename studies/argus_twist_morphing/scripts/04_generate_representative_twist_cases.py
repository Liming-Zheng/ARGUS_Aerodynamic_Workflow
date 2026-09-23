from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for rel in ["python/openvsp", "python/openvsp_config", "python/degen_geom", "python/utilities"]:
        sys.path.insert(0, str(root / rel))
    import openvsp as vsp

    return vsp


def parm(vsp, geom_id, name, group, default=0.0):
    parm_id = vsp.FindParm(geom_id, name, group)
    return vsp.GetParmVal(parm_id) if parm_id else default


def smoothstep(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def shape_factor(eta, eta_start, eta_end, shape_type, transition_fraction=0.15):
    if eta <= eta_start or eta >= eta_end:
        return 0.0
    r = (eta - eta_start) / (eta_end - eta_start)
    if shape_type == "uniform":
        raw = 1.0
    elif shape_type == "bell":
        raw = math.sin(math.pi * r)
    else:
        raise ValueError(f"Unknown twist shape {shape_type!r}")
    edge = transition_fraction
    if r < edge:
        window = smoothstep(r / edge)
    elif r > 1.0 - edge:
        window = smoothstep((1.0 - r) / edge)
    else:
        window = 1.0
    return raw * window


def section_rows(vsp, wing_id):
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsurf)
    semi_span = parm(vsp, wing_id, "TotalSpan", "WingGeom") / 2.0
    y = 0.0
    rows = []
    for index in range(count):
        if index:
            y += parm(vsp, wing_id, "ProjectedSpan", f"XSec_{index}")
        xsec = vsp.GetXSec(xsurf, index)
        rows.append(
            {
                "section_id": index,
                "eta": y / semi_span,
                "y_m": y,
                "chord_m": vsp.GetXSecWidth(xsec),
                "baseline_twist_deg": parm(vsp, wing_id, "Twist", f"XSec_{index}"),
                "twist_location_x_over_c": parm(
                    vsp, wing_id, "Twist_Location", f"XSec_{index}", 0.25
                ),
                "xsec_shape": vsp.GetXSecShape(xsec),
            }
        )
    return rows


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    study = json.loads(
        (args.project / "config" / "twist_study_config.json").read_text(encoding="utf-8")
    )
    cases = json.loads(
        (args.project / "config" / "representative_twist_cases.json").read_text(
            encoding="utf-8"
        )
    )
    baseline = (
        args.project
        / "outputs"
        / "refined_baseline"
        / "baseline_wing_only_refined.vsp3"
    )
    output_root = args.project / "outputs" / "representative_cases"
    output_root.mkdir(parents=True, exist_ok=True)
    vsp = load_vsp(args.openvsp_root)
    manifest = []

    for case in cases:
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(baseline))
        wing_id = vsp.FindGeom(study["wing_name"], 0)
        rows = section_rows(vsp, wing_id)
        schedule = []
        for row in rows:
            factor = shape_factor(
                row["eta"],
                study["eta_start"],
                study["eta_end"],
                case["shape_type"],
            )
            increment = case["twist_max_deg"] * factor
            final_twist = row["baseline_twist_deg"] + increment
            twist_id = vsp.FindParm(
                wing_id, "Twist", f"XSec_{row['section_id']}"
            )
            location_id = vsp.FindParm(
                wing_id, "Twist_Location", f"XSec_{row['section_id']}"
            )
            if twist_id:
                vsp.SetParmVal(twist_id, final_twist)
            if location_id:
                vsp.SetParmVal(location_id, study["rotation_axis_x_over_c"])
            schedule.append(
                {
                    **row,
                    "shape_type": case["shape_type"],
                    "shape_factor": factor,
                    "incremental_twist_deg": increment,
                    "final_twist_deg": final_twist,
                    "in_morph_region": study["eta_start"]
                    <= row["eta"]
                    <= study["eta_end"],
                }
            )
        vsp.Update()
        case_dir = output_root / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        model = case_dir / f"{case['case_id']}.vsp3"
        vsp.SetVSP3FileName(str(model))
        vsp.WriteVSPFile(str(model), vsp.SET_ALL)
        design = {
            **case,
            "eta_start": study["eta_start"],
            "eta_end": study["eta_end"],
            "rotation_axis_x_over_c": study["rotation_axis_x_over_c"],
            "baseline_model": str(baseline),
        }
        (case_dir / f"{case['case_id']}_design.json").write_text(
            json.dumps(design, indent=2) + "\n", encoding="utf-8"
        )
        write_csv(case_dir / f"{case['case_id']}_twist_schedule.csv", schedule)
        manifest.append(
            {
                "case_id": case["case_id"],
                "shape_type": case["shape_type"],
                "twist_max_deg": case["twist_max_deg"],
                "max_abs_incremental_twist_deg": max(
                    abs(row["incremental_twist_deg"]) for row in schedule
                ),
                "rotation_axis_x_over_c": study["rotation_axis_x_over_c"],
                "model": str(model),
            }
        )
        print(f"Generated {case['case_id']}")

    write_csv(output_root / "representative_twist_manifest.csv", manifest)


if __name__ == "__main__":
    main()



