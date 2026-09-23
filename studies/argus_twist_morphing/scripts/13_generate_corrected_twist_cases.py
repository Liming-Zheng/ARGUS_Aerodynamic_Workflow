from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--baseline-model", type=Path, required=True)
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
        rows.append({
            "section_id": index,
            "eta": y / semi_span,
            "y_native_ft": y,
            "chord_native_ft": vsp.GetXSecWidth(xsec),
            "baseline_twist_deg": parm(vsp, wing_id, "Twist", f"XSec_{index}"),
            "twist_location_x_over_c": parm(
                vsp, wing_id, "Twist_Location", f"XSec_{index}", 0.25
            ),
            "xsec_shape": vsp.GetXSecShape(xsec),
        })
    return rows


def interp_control(
    eta: float,
    eta_start: float,
    eta_end: float,
    control_etas: list[float],
    values: list[float],
) -> float:
    """Interpolate twist with a zero command at the fixed/morphing junction.

    The tip is part of the morphing region, so the final control value remains
    active at eta=1 instead of being forced back to zero.
    """
    if eta <= eta_start or eta > eta_end:
        return 0.0
    if eta < control_etas[0]:
        fraction = (eta - eta_start) / (control_etas[0] - eta_start)
        return fraction * values[0]
    if eta >= control_etas[-1]:
        return values[-1]
    for index in range(1, len(control_etas)):
        if eta <= control_etas[index]:
            left_eta = control_etas[index - 1]
            right_eta = control_etas[index]
            fraction = (eta - left_eta) / (right_eta - left_eta)
            return values[index - 1] + fraction * (values[index] - values[index - 1])
    return 0.0


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    project = args.project.resolve()
    study = json.loads((project / "config" / "twist_study_config.json").read_text(encoding="utf-8"))
    cases_path = args.cases if args.cases.is_absolute() else project / args.cases
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    baseline = args.baseline_model.resolve()
    output_root = args.output_root or project / "outputs" / "optimization" / "samples"
    output_root.mkdir(parents=True, exist_ok=True)
    vsp = load_vsp(args.openvsp_root)
    manifest = []

    for case in cases:
        control_etas = [float(value) for value in case["control_etas"]]
        control_twist = [float(value) for value in case["control_twist_deg"]]
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(baseline))
        wing_id = vsp.FindGeom(study["wing_name"], 0)
        rows = section_rows(vsp, wing_id)
        schedule = []
        for row in rows:
            increment = interp_control(
                row["eta"],
                float(case["eta_start"]),
                float(case["eta_end"]),
                control_etas,
                control_twist,
            )
            final_twist = row["baseline_twist_deg"] + increment
            twist_id = vsp.FindParm(wing_id, "Twist", f"XSec_{row['section_id']}")
            location_id = vsp.FindParm(
                wing_id, "Twist_Location", f"XSec_{row['section_id']}"
            )
            if twist_id:
                vsp.SetParmVal(twist_id, final_twist)
            if location_id:
                vsp.SetParmVal(location_id, float(case["rotation_axis_x_over_c"]))
            schedule.append({
                **row,
                "incremental_twist_deg": increment,
                "final_twist_deg": final_twist,
                "in_morph_region": (
                    float(case["eta_start"]) <= row["eta"] <= float(case["eta_end"])
                ),
            })
        vsp.Update()
        case_dir = output_root / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        model = case_dir / f"{case['case_id']}.vsp3"
        vsp.SetVSP3FileName(str(model))
        vsp.WriteVSPFile(str(model), vsp.SET_ALL)
        design = {
            **case,
            "baseline_model": str(baseline),
        }
        (case_dir / f"{case['case_id']}_design.json").write_text(
            json.dumps(design, indent=2) + "\n", encoding="utf-8"
        )
        write_csv(case_dir / f"{case['case_id']}_twist_schedule.csv", schedule)
        manifest.append({
            "case_id": case["case_id"],
            "max_abs_incremental_twist_deg": max(abs(value) for value in control_twist),
            "max_adjacent_twist_delta_deg": max(
                abs(right - left) for left, right in zip(control_twist, control_twist[1:])
            ),
            "rotation_axis_x_over_c": case["rotation_axis_x_over_c"],
            "model": str(model),
        })
        print(f"Generated {case['case_id']}")

    write_csv(output_root / "twist_optimization_manifest.csv", manifest)


if __name__ == "__main__":
    main()


