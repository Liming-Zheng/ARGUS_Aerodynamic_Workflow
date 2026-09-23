from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from bisect import bisect_right
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--eta-start", type=float, default=0.55)
    parser.add_argument("--eta-end", type=float, default=0.95)
    parser.add_argument(
        "--max-segment-eta",
        type=float,
        default=0.05,
        help="Maximum eta width for any geometric wing segment intersecting the refinement region.",
    )
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for rel in ["python/openvsp", "python/openvsp_config", "python/degen_geom", "python/utilities"]:
        sys.path.insert(0, str(root / rel))
    import openvsp as vsp

    return vsp


def parm(vsp, wing_id, name, group, default=0.0):
    parm_id = vsp.FindParm(wing_id, name, group)
    return vsp.GetParmVal(parm_id) if parm_id else default


def section_rows(vsp, wing_id):
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsurf)
    semi_span = parm(vsp, wing_id, "TotalSpan", "WingGeom") / 2.0
    y = 0.0
    rows = []
    for index in range(count):
        span = parm(vsp, wing_id, "ProjectedSpan", f"XSec_{index}") if index else 0.0
        y_start = y
        y += span
        rows.append({
            "section_id": index,
            "eta_start": y_start / semi_span,
            "eta_end": y / semi_span,
            "segment_eta": span / semi_span,
            "y_start": y_start,
            "y_end": y,
            "span": span,
            "chord": vsp.GetXSecWidth(vsp.GetXSec(xsurf, index)),
            "twist_increment_deg": parm(vsp, wing_id, "Twist", f"XSec_{index}"),
            "sweep_deg": parm(vsp, wing_id, "Sweep", f"XSec_{index}"),
            "dihedral_deg": parm(vsp, wing_id, "Dihedral", f"XSec_{index}"),
        })
    return rows


def intersects(row, eta_start, eta_end):
    return row["eta_end"] > eta_start and row["eta_start"] < eta_end


def refine(vsp, wing_id, eta_start, eta_end, max_segment_eta):
    split_count = 0
    while True:
        rows = section_rows(vsp, wing_id)
        candidate = next(
            (
                row
                for row in rows[1:]
                if intersects(row, eta_start, eta_end)
                and row["segment_eta"] > max_segment_eta + 1.0e-10
            ),
            None,
        )
        if candidate is None:
            return split_count
        vsp.SplitWingXSec(wing_id, candidate["section_id"])
        vsp.Update()
        split_count += 1


def interpolate_original_twist(original_rows, eta):
    etas = [row["eta_end"] for row in original_rows]
    twists = [row["twist_increment_deg"] for row in original_rows]
    if eta <= etas[0]:
        return twists[0]
    if eta >= etas[-1]:
        return twists[-1]
    right = bisect_right(etas, eta)
    left = right - 1
    fraction = (eta - etas[left]) / (etas[right] - etas[left])
    return twists[left] + fraction * (twists[right] - twists[left])


def restore_twist_distribution(vsp, wing_id, original_rows):
    rows = section_rows(vsp, wing_id)
    for row in rows:
        parm_id = vsp.FindParm(wing_id, "Twist", f"XSec_{row['section_id']}")
        if parm_id:
            vsp.SetParmVal(
                parm_id,
                interpolate_original_twist(original_rows, row["eta_end"]),
            )
    vsp.Update()


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def set_int(vsp, analysis, name, value):
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetIntAnalysisInput(analysis, name, [int(value)], 0)


def set_double(vsp, analysis, name, value):
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetDoubleAnalysisInput(analysis, name, [float(value)], 0)


def set_string(vsp, analysis, name, value):
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetStringAnalysisInput(analysis, name, [str(value)], 0)


def last(vsp, result_id, names):
    for name in names:
        try:
            values = list(vsp.GetDoubleResults(result_id, name))
        except Exception:
            values = []
        if values:
            return values[-1]
    return ""


def run_reference_case(vsp, wing_id, config):
    analysis = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_NONE)
    set_int(vsp, analysis, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(analysis)

    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", config["reference_area_m2"])
    set_double(vsp, analysis, "cref", config["reference_chord_m"])
    set_double(vsp, analysis, "bref", config["reference_span_m"])
    set_string(vsp, analysis, "WingID", wing_id)
    for prefix, value in [
        ("Alpha", config["default_alpha_deg"]),
        ("Beta", config["beta_deg"]),
        ("Mach", config["mach"]),
    ]:
        set_double(vsp, analysis, f"{prefix}Start", value)
        set_double(vsp, analysis, f"{prefix}End", value)
        set_int(vsp, analysis, f"{prefix}Npts", 1)
    set_int(vsp, analysis, "WakeNumIter", config["wake_iterations"])
    vsp.ExecAnalysis(analysis)
    result_id = vsp.FindLatestResultsID("VSPAERO_History")
    return {
        "case_id": "refined_baseline",
        "alpha_deg": config["default_alpha_deg"],
        "mach": config["mach"],
        "CL": last(vsp, result_id, ["CLtot", "CL"]),
        "CD": last(vsp, result_id, ["CDtot", "CD"]),
        "CDi": last(vsp, result_id, ["CDi"]),
        "Cm": last(vsp, result_id, ["CMytot", "CMy", "Cm"]),
    }


def main():
    args = parse_args()
    config = json.loads(
        (args.project / "config" / "baseline_config.json").read_text(encoding="utf-8")
    )
    source = args.project / "outputs" / "baseline" / "baseline_wing_only.vsp3"
    output = args.project / "outputs" / "refined_baseline"
    output.mkdir(parents=True, exist_ok=True)
    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(source))
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    before = {
        "xsec_count": vsp.GetNumXSec(vsp.GetXSecSurf(wing_id, 0)),
        "span": parm(vsp, wing_id, "TotalSpan", "WingGeom"),
        "area": parm(vsp, wing_id, "TotalArea", "WingGeom"),
        "mac": parm(vsp, wing_id, "MAC", "WingGeom"),
        "aspect_ratio": parm(vsp, wing_id, "TotalAR", "WingGeom"),
    }
    original_rows = section_rows(vsp, wing_id)
    split_count = refine(
        vsp,
        wing_id,
        args.eta_start,
        args.eta_end,
        args.max_segment_eta,
    )
    restore_twist_distribution(vsp, wing_id, original_rows)
    rows = section_rows(vsp, wing_id)
    after = {
        "xsec_count": len(rows),
        "span": parm(vsp, wing_id, "TotalSpan", "WingGeom"),
        "area": parm(vsp, wing_id, "TotalArea", "WingGeom"),
        "mac": parm(vsp, wing_id, "MAC", "WingGeom"),
        "aspect_ratio": parm(vsp, wing_id, "TotalAR", "WingGeom"),
    }
    model = output / "baseline_wing_only_refined.vsp3"
    vsp.SetVSP3FileName(str(model))
    vsp.WriteVSPFile(str(model), vsp.SET_ALL)
    write_csv(output / "refined_section_table.csv", rows)
    comparison = []
    for name in before:
        comparison.append({
            "parameter": name,
            "before": before[name],
            "after": after[name],
            "difference": after[name] - before[name],
        })
    write_csv(output / "refinement_geometry_comparison.csv", comparison)
    result = run_reference_case(vsp, wing_id, config)
    write_csv(output / "refined_baseline_vspaero_coefficients.csv", [result])
    metadata = {
        "eta_start": args.eta_start,
        "eta_end": args.eta_end,
        "max_segment_eta": args.max_segment_eta,
        "split_count": split_count,
        "morph_region_geometric_sections": sum(
            args.eta_start <= row["eta_end"] <= args.eta_end for row in rows
        ),
    }
    (output / "refinement_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2))
    print(f"Wrote refined baseline to {model}")


if __name__ == "__main__":
    main()


