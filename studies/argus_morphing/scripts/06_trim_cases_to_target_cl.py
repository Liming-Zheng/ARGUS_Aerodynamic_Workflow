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
    parser.add_argument("--alpha-low", type=float, default=1.0)
    parser.add_argument("--alpha-high", type=float, default=3.0)
    parser.add_argument("--cl-tolerance", type=float, default=2.0e-4)
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for rel in ["python/openvsp", "python/openvsp_config", "python/degen_geom", "python/utilities"]:
        sys.path.insert(0, str(root / rel))
    import openvsp as vsp

    return vsp


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
    return float("nan")


def configure_geometry(vsp, method):
    analysis = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", method)
    set_int(vsp, analysis, "GeomSet", vsp.SET_NONE)
    set_int(vsp, analysis, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(analysis)


def evaluate(vsp, wing_id, alpha, mach, config):
    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", config["reference_area_m2"])
    set_double(vsp, analysis, "cref", config["reference_chord_m"])
    set_double(vsp, analysis, "bref", config["reference_span_m"])
    set_string(vsp, analysis, "WingID", wing_id)
    for prefix, value in [("Alpha", alpha), ("Beta", 0.0), ("Mach", mach)]:
        set_double(vsp, analysis, f"{prefix}Start", value)
        set_double(vsp, analysis, f"{prefix}End", value)
        set_int(vsp, analysis, f"{prefix}Npts", 1)
    set_int(vsp, analysis, "WakeNumIter", config["wake_iterations"])
    vsp.ExecAnalysis(analysis)
    result_id = vsp.FindLatestResultsID("VSPAERO_History")
    return {
        "alpha_deg": alpha,
        "CL": last(vsp, result_id, ["CLtot", "CL"]),
        "CD": last(vsp, result_id, ["CDtot", "CD"]),
        "CDi": last(vsp, result_id, ["CDi"]),
        "Cm": last(vsp, result_id, ["CMytot", "CMy", "Cm"]),
    }


def target_cl(project: Path, default_alpha: float) -> float:
    path = project / "outputs" / "baseline" / "baseline_vspaero_coefficients.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    row = min(rows, key=lambda item: abs(float(item["alpha_deg"]) - default_alpha))
    return float(row["CL"])


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    config = json.loads(
        (args.project / "config" / "baseline_config.json").read_text(encoding="utf-8")
    )
    cl_target = target_cl(args.project, config["default_alpha_deg"])
    cases_root = args.project / "outputs" / "cases"
    vsp = load_vsp(args.openvsp_root)
    summary = []
    for case_dir in sorted(path for path in cases_root.iterdir() if path.is_dir()):
        design = json.loads(next(case_dir.glob("*_design.json")).read_text(encoding="utf-8"))
        model = case_dir / f"{design['case_id']}.vsp3"
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(model))
        vsp.Update()
        wing_id = vsp.FindGeom("cruise_wing", 0)
        configure_geometry(vsp, config["analysis_method"])
        low = evaluate(vsp, wing_id, args.alpha_low, design["mach"], config)
        high = evaluate(vsp, wing_id, args.alpha_high, design["mach"], config)
        slope = (high["CL"] - low["CL"]) / (args.alpha_high - args.alpha_low)
        if abs(slope) < 1.0e-8:
            raise RuntimeError(f"Near-zero lift slope for {design['case_id']}")
        alpha_trim = args.alpha_low + (cl_target - low["CL"]) / slope
        trimmed = evaluate(vsp, wing_id, alpha_trim, design["mach"], config)
        evaluation_count = 3
        for _ in range(3):
            if abs(trimmed["CL"] - cl_target) <= args.cl_tolerance:
                break
            alpha_trim += (cl_target - trimmed["CL"]) / slope
            trimmed = evaluate(vsp, wing_id, alpha_trim, design["mach"], config)
            evaluation_count += 1
        row = {
            "case_id": design["case_id"],
            "shape_type": design["shape_type"],
            "x_h_over_c": design["x_h_over_c"],
            "A_max_over_c": design["A_max_over_c"],
            "CL_target": cl_target,
            "alpha_trim_deg": alpha_trim,
            "CL": trimmed["CL"],
            "CL_error": trimmed["CL"] - cl_target,
            "CD": trimmed["CD"],
            "CDi": trimmed["CDi"],
            "Cm": trimmed["Cm"],
            "lift_curve_slope_per_deg": slope,
            "trim_converged": abs(trimmed["CL"] - cl_target) <= args.cl_tolerance,
            "evaluation_count": evaluation_count,
        }
        summary.append(row)
        write_csv(case_dir / f"{design['case_id']}_fixed_cl_trim.csv", [row])
        print(
            f"{design['case_id']}: alpha={alpha_trim:.4f}, "
            f"CL={trimmed['CL']:.6f}, CDi={trimmed['CDi']:.6f}"
        )
    write_csv(cases_root / "representative_fixed_cl_summary.csv", summary)
    print(f"Fixed-CL evaluation complete; CL_target={cl_target:.9f}")


if __name__ == "__main__":
    main()


