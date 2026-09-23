from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")
DEFAULT_PYTHON = Path(r"<OPENVSP_PYTHON>")
TARGET_CL = 0.428277635108


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cl-tolerance", type=float, default=2.0e-5)
    parser.add_argument("--max-iterations", type=int, default=6)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case-dir", type=Path)
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
    return float("nan")


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


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
        output.append({
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
        })
    return output


def load_metrics(rows):
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


def max_adjacent(values: list[float]) -> float:
    return max(abs(right - left) for left, right in zip(values, values[1:]))


def worker(args):
    project = args.project.resolve()
    case_dir = args.case_dir.resolve()
    case_id = case_dir.name
    result_path = case_dir / f"{case_id}_optimization_result.csv"
    if result_path.exists() and not args.force:
        return
    started = time.perf_counter()
    config = json.loads((project / "config" / "baseline_config.json").read_text(encoding="utf-8"))
    design = json.loads((case_dir / f"{case_id}_design.json").read_text(encoding="utf-8"))
    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(case_dir / f"{case_id}.vsp3"))
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    configure_geometry(vsp, config)
    final, raw, trace = trim(vsp, wing_id, config, args.cl_tolerance, args.max_iterations)
    loads = collapse_loads(
        raw,
        case_id,
        config,
        float(design["eta_start"]),
        float(design["eta_end"]),
    )
    metrics = load_metrics(loads)
    baseline = next(
        row for row in read_csv(project / "outputs" / "fixed_cl_doe" / "fixed_cl_twist_doe_summary.csv")
        if row["case_id"] == "twist_baseline"
    )
    baseline_bending = float(baseline["half_wing_root_bending_moment_Nm"])
    baseline_cdi = float(baseline["CDi"])
    twist_values = [float(value) for value in design["control_twist_deg"]]
    row = {
        "case_id": case_id,
        **{f"T{i+1}_deg": value for i, value in enumerate(twist_values)},
        "alpha_trim_deg": final["alpha_deg"],
        "CL_target": TARGET_CL,
        "CL": final["CL"],
        "CL_error": final["CL"] - TARGET_CL,
        "CD": final["CD"],
        "CDi": final["CDi"],
        "CDi_reduction_percent": 100.0 * (baseline_cdi - final["CDi"]) / baseline_cdi,
        "Cm": final["Cm"],
        **metrics,
        "root_bending_change_percent": 100.0
        * (metrics["half_wing_root_bending_moment_Nm"] - baseline_bending)
        / baseline_bending,
        "max_adjacent_twist_delta_deg": max_adjacent(twist_values),
        "max_abs_twist_deg": max(abs(value) for value in twist_values),
        "evaluation_seconds": time.perf_counter() - started,
    }
    write_csv(result_path, [row])
    write_csv(case_dir / f"{case_id}_trim_trace.csv", trace)
    write_csv(case_dir / f"{case_id}_spanwise_loads.csv", loads)


def launch(args, case_dir):
    command = [
        str(args.python),
        str(Path(__file__).resolve()),
        "--worker",
        "--project",
        str(args.project.resolve()),
        "--openvsp-root",
        str(args.openvsp_root),
        "--case-dir",
        str(case_dir.resolve()),
        "--cl-tolerance",
        str(args.cl_tolerance),
        "--max-iterations",
        str(args.max_iterations),
    ]
    if args.force:
        command.append("--force")
    temp_dir = case_dir / "_worker_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["TEMP"] = str(temp_dir)
    environment["TMP"] = str(temp_dir)
    completed = subprocess.run(
        command,
        cwd=case_dir,
        env=environment,
        capture_output=True,
        text=True,
    )
    (case_dir / f"{case_dir.name}_optimization.log").write_text(
        completed.stdout + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(f"{case_dir.name} failed")
    return case_dir.name


def aggregate(project: Path) -> int:
    rows = []
    root = project / "outputs" / "optimization" / "samples"
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        result = case_dir / f"{case_dir.name}_optimization_result.csv"
        if result.exists():
            rows.extend(read_csv(result))
    if rows:
        write_csv(project / "outputs" / "optimization" / "optimization_samples.csv", rows)
    return len(rows)


def main():
    args = parse_args()
    if args.worker:
        worker(args)
        return
    root = args.project / "outputs" / "optimization" / "samples"
    pending = [
        path for path in sorted(root.iterdir()) if path.is_dir()
        and (args.force or not (path / f"{path.name}_optimization_result.csv").exists())
    ]
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(launch, args, path): path for path in pending}
        for future in as_completed(futures):
            path = futures[future]
            try:
                print(f"complete: {future.result()}")
            except Exception as exc:
                failures.append(path)
                print(f"failed: {path.name}: {exc}")
    count = aggregate(args.project)
    print(f"Twist optimization samples complete={count}, failed={len(failures)}")
    if failures:
        raise RuntimeError(f"{len(failures)} samples failed")


if __name__ == "__main__":
    main()


