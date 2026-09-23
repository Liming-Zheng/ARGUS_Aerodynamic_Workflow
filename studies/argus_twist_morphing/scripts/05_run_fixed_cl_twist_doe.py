from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")
TARGET_CL = 0.428277635108


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--cl-tolerance", type=float, default=2.0e-5)
    parser.add_argument("--max-iterations", type=int, default=6)
    return parser.parse_args()


def load_vsp(root):
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


def doubles(vsp, result_id, name):
    try:
        return list(vsp.GetDoubleResults(result_id, name))
    except Exception:
        return []


def last(vsp, result_id, names):
    for name in names:
        values = doubles(vsp, result_id, name)
        if values:
            return values[-1]
    return float("nan")


def write_csv(path, rows):
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def configure_geometry(vsp, config):
    analysis = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_NONE)
    set_int(vsp, analysis, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(analysis)


def evaluate(vsp, wing_id, alpha, config, include_loads=False):
    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", config["reference_area_m2"])
    set_double(vsp, analysis, "cref", config["reference_chord_m"])
    set_double(vsp, analysis, "bref", config["reference_span_m"])
    set_string(vsp, analysis, "WingID", wing_id)
    for prefix, value in [("Alpha", alpha), ("Beta", 0.0), ("Mach", config["mach"])]:
        set_double(vsp, analysis, f"{prefix}Start", value)
        set_double(vsp, analysis, f"{prefix}End", value)
        set_int(vsp, analysis, f"{prefix}Npts", 1)
    set_int(vsp, analysis, "WakeNumIter", config["wake_iterations"])
    vsp.ExecAnalysis(analysis)
    history = vsp.FindLatestResultsID("VSPAERO_History")
    result = {
        "alpha_deg": alpha,
        "CL": last(vsp, history, ["CLtot", "CL"]),
        "CD": last(vsp, history, ["CDtot", "CD"]),
        "CDi": last(vsp, history, ["CDi"]),
        "Cm": last(vsp, history, ["CMytot", "CMy", "Cm"]),
    }
    if not include_loads:
        return result, []
    load_id = vsp.FindLatestResultsID("VSPAERO_Load")
    names = list(vsp.GetAllDataNames(load_id))
    columns = {name: doubles(vsp, load_id, name) for name in names}
    count = max((len(values) for values in columns.values()), default=0)
    loads = []
    for index in range(count):
        row = {"station_index": index}
        for name, values in columns.items():
            if index < len(values):
                row[name] = values[index]
        loads.append(row)
    return result, loads


def trim(vsp, wing_id, config, tolerance, max_iterations):
    p0, _ = evaluate(vsp, wing_id, 1.5, config)
    p1, _ = evaluate(vsp, wing_id, 2.5, config)
    trace = [p0, p1]
    for _ in range(max_iterations):
        alpha = p1["alpha_deg"] + (TARGET_CL - p1["CL"]) * (
            p1["alpha_deg"] - p0["alpha_deg"]
        ) / (p1["CL"] - p0["CL"])
        point, _ = evaluate(vsp, wing_id, alpha, config)
        trace.append(point)
        if abs(point["CL"] - TARGET_CL) <= tolerance:
            final, loads = evaluate(vsp, wing_id, alpha, config, include_loads=True)
            return final, loads, trace
        p0, p1 = p1, point
    raise RuntimeError(f"Trim failed, final CL={p1['CL']}")


def collapse_loads(raw_rows, case_id, config, eta_start, eta_end):
    q = 0.5 * config["rho_kg_m3"] * config["velocity_m_s"] ** 2
    semi_span = config["reference_span_m"] / 2.0
    bins = defaultdict(list)
    for row in raw_rows:
        bins[round(abs(float(row.get("Yavg", 0.0))), 8)].append(row)
    output = []
    for y in sorted(bins):
        items = bins[y]

        def avg(name):
            return sum(float(item.get(name, 0.0)) for item in items) / len(items)

        chord = avg("Chord")
        eta = y / semi_span
        output.append(
            {
                "case_id": case_id,
                "eta": eta,
                "y_m": y,
                "dy_m": avg("dSpan"),
                "chord_m": chord,
                "sectional_cl": avg("cl"),
                "sectional_cd": avg("cd"),
                "lift_per_span_N_per_m": q * chord * avg("cl"),
                "drag_per_span_N_per_m": q * chord * avg("cd"),
                "section_pitch_moment_N": q * chord**2 * avg("cmy"),
                "in_morph_region": eta_start <= eta <= eta_end,
            }
        )
    return output


def metrics(rows):
    total_lift = sum(row["lift_per_span_N_per_m"] * row["dy_m"] for row in rows)
    root_bending = sum(
        row["lift_per_span_N_per_m"] * row["dy_m"] * row["y_m"] for row in rows
    )
    outer = [row for row in rows if row["in_morph_region"]]
    outer_lift = sum(row["lift_per_span_N_per_m"] * row["dy_m"] for row in outer)
    outer_pitch = sum(row["section_pitch_moment_N"] * row["dy_m"] for row in outer)
    return {
        "half_wing_lift_N": total_lift,
        "half_wing_root_bending_moment_Nm": root_bending,
        "morph_region_lift_N": outer_lift,
        "morph_region_lift_fraction": outer_lift / total_lift,
        "morph_region_pitch_moment_proxy_Nm": outer_pitch,
    }


def main():
    args = parse_args()
    config = json.loads(
        (args.project / "config" / "baseline_config.json").read_text(encoding="utf-8")
    )
    study = json.loads(
        (args.project / "config" / "twist_study_config.json").read_text(encoding="utf-8")
    )
    root = args.project / "outputs" / "representative_cases"
    output = args.project / "outputs" / "fixed_cl_doe"
    output.mkdir(parents=True, exist_ok=True)
    designs = []
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        design_path = next(case_dir.glob("*_design.json"))
        design = json.loads(design_path.read_text(encoding="utf-8"))
        design["model"] = case_dir / f"{design['case_id']}.vsp3"
        designs.append(design)
    vsp = load_vsp(args.openvsp_root)
    summary = []
    for design in designs:
        case_id = design["case_id"]
        print(f"Fixed-CL evaluation: {case_id}")
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(design["model"]))
        wing_id = vsp.FindGeom(config["wing_name"], 0)
        configure_geometry(vsp, config)
        final, raw, trace = trim(
            vsp, wing_id, config, args.cl_tolerance, args.max_iterations
        )
        loads = collapse_loads(
            raw, case_id, config, study["eta_start"], study["eta_end"]
        )
        row = {
            "case_id": case_id,
            "shape_type": design["shape_type"],
            "twist_max_deg": design["twist_max_deg"],
            "alpha_trim_deg": final["alpha_deg"],
            "CL_target": TARGET_CL,
            "CL": final["CL"],
            "CD": final["CD"],
            "CDi": final["CDi"],
            "Cm": final["Cm"],
            **metrics(loads),
        }
        summary.append(row)
        write_csv(output / f"{case_id}_trim_trace.csv", trace)
        write_csv(output / f"{case_id}_spanwise_loads.csv", loads)
        write_csv(output / f"{case_id}_fixed_cl_summary.csv", [row])
    baseline = next(row for row in summary if row["case_id"] == "twist_baseline")
    for row in summary:
        row["CDi_change_percent"] = 100.0 * (row["CDi"] - baseline["CDi"]) / baseline["CDi"]
        row["CDi_reduction_percent"] = -row["CDi_change_percent"]
        row["root_bending_change_percent"] = 100.0 * (
            row["half_wing_root_bending_moment_Nm"]
            - baseline["half_wing_root_bending_moment_Nm"]
        ) / baseline["half_wing_root_bending_moment_Nm"]
        row["outer_lift_change_percent"] = 100.0 * (
            row["morph_region_lift_N"] - baseline["morph_region_lift_N"]
        ) / baseline["morph_region_lift_N"]
    write_csv(output / "fixed_cl_twist_doe_summary.csv", summary)
    print(f"Wrote {len(summary)} fixed-CL cases to {output}")


if __name__ == "__main__":
    main()


