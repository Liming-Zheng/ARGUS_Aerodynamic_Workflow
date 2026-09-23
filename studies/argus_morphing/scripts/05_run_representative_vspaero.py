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
    return ""


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def run_case(vsp, case_dir: Path, baseline_config: dict):
    design_path = next(case_dir.glob("*_design.json"))
    design = json.loads(design_path.read_text(encoding="utf-8"))
    model_path = case_dir / f"{design['case_id']}.vsp3"
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(model_path))
    vsp.Update()
    wing_id = vsp.FindGeom("cruise_wing", 0)
    compute = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(compute)
    set_int(vsp, compute, "AnalysisMethod", baseline_config["analysis_method"])
    set_int(vsp, compute, "GeomSet", vsp.SET_NONE)
    set_int(vsp, compute, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(compute)

    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", baseline_config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", baseline_config["reference_area_m2"])
    set_double(vsp, analysis, "cref", baseline_config["reference_chord_m"])
    set_double(vsp, analysis, "bref", baseline_config["reference_span_m"])
    set_string(vsp, analysis, "WingID", wing_id)
    for prefix, value in [
        ("Alpha", design["alpha_deg"]),
        ("Beta", 0.0),
        ("Mach", design["mach"]),
    ]:
        set_double(vsp, analysis, f"{prefix}Start", value)
        set_double(vsp, analysis, f"{prefix}End", value)
        set_int(vsp, analysis, f"{prefix}Npts", 1)
    set_int(vsp, analysis, "WakeNumIter", baseline_config["wake_iterations"])
    vsp.ExecAnalysis(analysis)
    history_id = vsp.FindLatestResultsID("VSPAERO_History")
    load_id = vsp.FindLatestResultsID("VSPAERO_Load")
    coefficient = {
        "case_id": design["case_id"],
        "alpha_deg": design["alpha_deg"],
        "mach": design["mach"],
        "x_h_over_c": design["x_h_over_c"],
        "eta_start": design["eta_start"],
        "eta_end": design["eta_end"],
        "A_max_over_c": design["A_max_over_c"],
        "shape_type": design["shape_type"],
        "CL": last(vsp, history_id, ["CLtot", "CL"]),
        "CD": last(vsp, history_id, ["CDtot", "CD"]),
        "CDi": last(vsp, history_id, ["CDi"]),
        "Cm": last(vsp, history_id, ["CMytot", "CMy", "Cm"]),
    }
    names = list(vsp.GetAllDataNames(load_id))
    columns = {name: doubles(vsp, load_id, name) for name in names}
    count = max((len(values) for values in columns.values()), default=0)
    loads = []
    for index in range(count):
        row = {"case_id": design["case_id"], "station_index": index}
        for name, values in columns.items():
            if index < len(values):
                row[name] = values[index]
        loads.append(row)
    write_csv(
        case_dir / f"{design['case_id']}_vspaero_coefficients.csv",
        [coefficient],
        list(coefficient),
    )
    fields = ["case_id", "station_index"] + sorted(
        set().union(*(row.keys() for row in loads)) - {"case_id", "station_index"}
    )
    write_csv(case_dir / f"{design['case_id']}_vspaero_load_raw.csv", loads, fields)
    return coefficient


def main():
    args = parse_args()
    baseline_config = json.loads(
        (args.project / "config" / "baseline_config.json").read_text(encoding="utf-8")
    )
    cases_root = args.project / "outputs" / "cases"
    vsp = load_vsp(args.openvsp_root)
    rows = []
    for case_dir in sorted(path for path in cases_root.iterdir() if path.is_dir()):
        print(f"Running {case_dir.name}")
        rows.append(run_case(vsp, case_dir, baseline_config))
    fields = list(rows[0])
    write_csv(cases_root / "representative_vspaero_summary.csv", rows, fields)
    print(f"Completed {len(rows)} representative VSPAERO cases")


if __name__ == "__main__":
    main()


