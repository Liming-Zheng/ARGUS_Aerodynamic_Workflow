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


def load_vsp(root):
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


def uniform_factor(eta, eta_start, eta_end, transition_fraction):
    if eta <= eta_start or eta >= eta_end:
        return 0.0
    fraction = (eta - eta_start) / (eta_end - eta_start)
    if fraction < transition_fraction:
        return smoothstep(fraction / transition_fraction)
    if fraction > 1.0 - transition_fraction:
        return smoothstep((1.0 - fraction) / transition_fraction)
    return 1.0


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
                "baseline_twist_location_x_over_c": parm(
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


def axis_tag(axis):
    return f"x{round(100 * axis):02d}"


def main():
    args = parse_args()
    study = json.loads(
        (args.project / "config" / "twist_study_config.json").read_text(encoding="utf-8")
    )
    sensitivity = json.loads(
        (args.project / "config" / "axis_sensitivity_config.json").read_text(
            encoding="utf-8"
        )
    )
    baseline = (
        args.project / "outputs" / "refined_baseline" / "baseline_wing_only_refined.vsp3"
    )
    output_root = args.project / "outputs" / "axis_sensitivity_cases"
    output_root.mkdir(parents=True, exist_ok=True)
    vsp = load_vsp(args.openvsp_root)
    manifest = []

    for axis in sensitivity["axis_locations_x_over_c"]:
        for command in sensitivity["twist_cases"]:
            case_id = f"axis_{axis_tag(axis)}_{command['case_name']}"
            vsp.ClearVSPModel()
            vsp.ReadVSPFile(str(baseline))
            wing_id = vsp.FindGeom(study["wing_name"], 0)
            original = section_rows(vsp, wing_id)
            schedule = []
            for row in original:
                factor = uniform_factor(
                    row["eta"],
                    study["eta_start"],
                    study["eta_end"],
                    sensitivity["transition_fraction"],
                )
                increment = command["twist_max_deg"] * factor
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
                    vsp.SetParmVal(location_id, axis)

                angle = math.radians(increment)
                # The inherited section-table key predates the unit audit:
                # chord_m contains native OpenVSP feet.
                chord_m = row["chord_m"] * 0.3048
                le_radius = axis * chord_m
                te_radius = (1.0 - axis) * chord_m
                schedule.append(
                    {
                        **row,
                        "case_id": case_id,
                        "axis_x_over_c": axis,
                        "shape_factor": factor,
                        "incremental_twist_deg": increment,
                        "final_twist_deg": final_twist,
                        "leading_edge_dx_m": le_radius * (1.0 - math.cos(angle)),
                        "leading_edge_dz_m": -le_radius * math.sin(angle),
                        "leading_edge_travel_m": 2.0
                        * le_radius
                        * math.sin(abs(angle) / 2.0),
                        "trailing_edge_dx_m": te_radius * (math.cos(angle) - 1.0),
                        "trailing_edge_dz_m": te_radius * math.sin(angle),
                        "trailing_edge_travel_m": 2.0
                        * te_radius
                        * math.sin(abs(angle) / 2.0),
                        "in_morph_region": study["eta_start"]
                        <= row["eta"]
                        <= study["eta_end"],
                    }
                )
            vsp.Update()
            case_dir = output_root / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            model = case_dir / f"{case_id}.vsp3"
            vsp.SetVSP3FileName(str(model))
            vsp.WriteVSPFile(str(model), vsp.SET_ALL)
            design = {
                "case_id": case_id,
                "case_name": command["case_name"],
                "shape_type": sensitivity["shape_type"],
                "twist_max_deg": command["twist_max_deg"],
                "axis_x_over_c": axis,
                "eta_start": study["eta_start"],
                "eta_end": study["eta_end"],
                "baseline_model": str(baseline),
                "comparison_baseline": f"axis_{axis_tag(axis)}_baseline",
            }
            (case_dir / f"{case_id}_design.json").write_text(
                json.dumps(design, indent=2) + "\n", encoding="utf-8"
            )
            write_csv(case_dir / f"{case_id}_twist_schedule.csv", schedule)
            manifest.append(
                {
                    **design,
                    "max_le_travel_mm": 1000.0
                    * max(row["leading_edge_travel_m"] for row in schedule),
                    "max_te_travel_mm": 1000.0
                    * max(row["trailing_edge_travel_m"] for row in schedule),
                    "model": str(model),
                }
            )
            print(f"Generated {case_id}")

    write_csv(output_root / "axis_sensitivity_manifest.csv", manifest)
    print(f"Wrote {len(manifest)} cases to {output_root}")


if __name__ == "__main__":
    main()


