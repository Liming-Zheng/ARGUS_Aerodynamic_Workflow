from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")
DEFAULT_PYTHON = Path(r"<OPENVSP_PYTHON>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
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


def last(vsp, result_id, names):
    for name in names:
        try:
            values = list(vsp.GetDoubleResults(result_id, name))
        except Exception:
            values = []
        if values:
            return values[-1]
    raise RuntimeError(f"None of result fields {names} were available")


def target_cl(project: Path) -> float:
    refined = project / "outputs" / "refined_baseline" / "refined_baseline_vspaero_coefficients.csv"
    with refined.open(newline="", encoding="utf-8-sig") as handle:
        return float(next(csv.DictReader(handle))["CL"])


def interpolate_at_cl(points: list[dict], cl_target: float, field: str) -> float:
    points = sorted(points, key=lambda row: row["CL"])
    if cl_target <= points[0]["CL"]:
        left, right = points[0], points[1]
    elif cl_target >= points[-1]["CL"]:
        left, right = points[-2], points[-1]
    else:
        right_index = next(i for i, row in enumerate(points) if row["CL"] >= cl_target)
        left, right = points[right_index - 1], points[right_index]
    fraction = (cl_target - left["CL"]) / (right["CL"] - left["CL"])
    return left[field] + fraction * (right[field] - left[field])


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def worker(args):
    if args.case_dir is None:
        raise ValueError("--case-dir is required in worker mode")
    project = args.project.resolve()
    case_dir = args.case_dir.resolve()
    case_id = case_dir.name
    result_path = case_dir / f"{case_id}_doe_fixed_cl.csv"
    if result_path.exists() and not args.force:
        return
    config = json.loads(
        (project / "config" / "baseline_config.json").read_text(encoding="utf-8")
    )
    design = json.loads(
        (case_dir / f"{case_id}_design.json").read_text(encoding="utf-8")
    )
    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(case_dir / f"{case_id}.vsp3"))
    vsp.Update()
    wing_id = vsp.FindGeom(config["wing_name"], 0)

    analysis = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_NONE)
    set_int(vsp, analysis, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(analysis)

    alphas = [1.0, 2.0, 3.0]
    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", config["reference_area_m2"])
    set_double(vsp, analysis, "cref", config["reference_chord_m"])
    set_double(vsp, analysis, "bref", config["reference_span_m"])
    set_string(vsp, analysis, "WingID", wing_id)
    set_double(vsp, analysis, "AlphaStart", alphas[0])
    set_double(vsp, analysis, "AlphaEnd", alphas[-1])
    set_int(vsp, analysis, "AlphaNpts", len(alphas))
    set_double(vsp, analysis, "MachStart", design["mach"])
    set_double(vsp, analysis, "MachEnd", design["mach"])
    set_int(vsp, analysis, "MachNpts", 1)
    set_int(vsp, analysis, "WakeNumIter", config["wake_iterations"])
    vsp.ExecAnalysis(analysis)

    count = vsp.GetNumResults("VSPAERO_History")
    if count < len(alphas):
        raise RuntimeError(f"Expected at least {len(alphas)} history results, found {count}")
    result_ids = [
        vsp.FindResultsID("VSPAERO_History", index)
        for index in range(count - len(alphas), count)
    ]
    points = []
    for alpha, result_id in zip(alphas, result_ids):
        points.append({
            "alpha_deg": alpha,
            "CL": last(vsp, result_id, ["CLtot", "CL"]),
            "CD": last(vsp, result_id, ["CDtot", "CD"]),
            "CDi": last(vsp, result_id, ["CDi"]),
            "Cm": last(vsp, result_id, ["CMytot", "CMy", "Cm"]),
        })
    cl_target = target_cl(project)
    row = {
        "case_id": case_id,
        "x_h_over_c": design["x_h_over_c"],
        "eta_start": design["eta_start"],
        "eta_end": design["eta_end"],
        "A_max_over_c": design["A_max_over_c"],
        "shape_type": design["shape_type"],
        "CL_target": cl_target,
        "alpha_trim_deg": interpolate_at_cl(points, cl_target, "alpha_deg"),
        "CL": cl_target,
        "CD": interpolate_at_cl(points, cl_target, "CD"),
        "CDi": interpolate_at_cl(points, cl_target, "CDi"),
        "Cm": interpolate_at_cl(points, cl_target, "Cm"),
        "evaluation_method": "three-point interpolation in CL using alpha=1,2,3 deg",
        "status": "complete",
    }
    write_csv(result_path, [row])
    write_csv(case_dir / f"{case_id}_doe_alpha_points.csv", points)


def launch_case(args, case_dir: Path):
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
    ]
    if args.force:
        command.append("--force")
    completed = subprocess.run(command, capture_output=True, text=True)
    log = case_dir / f"{case_dir.name}_doe_runner.log"
    log.write_text(completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"{case_dir.name} failed; see {log}")
    return case_dir.name


def aggregate(project: Path):
    root = project / "outputs" / "doe"
    rows = []
    failures = []
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        result = case_dir / f"{case_dir.name}_doe_fixed_cl.csv"
        if result.exists():
            with result.open(newline="", encoding="utf-8-sig") as handle:
                rows.append(next(csv.DictReader(handle)))
        else:
            failures.append({"case_id": case_dir.name, "reason": "result missing"})
    if rows:
        write_csv(root / "minimal_doe_fixed_cl_summary.csv", rows)
    with (root / "minimal_doe_failures.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "reason"])
        writer.writeheader()
        writer.writerows(failures)
    return len(rows), len(failures)


def fill_zero_amplitude_duplicates(project: Path):
    root = project / "outputs" / "doe"
    zero_cases = []
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        design_path = case_dir / f"{case_dir.name}_design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        if abs(float(design["A_max_over_c"])) < 1.0e-12:
            zero_cases.append(case_dir)
    source = next(
        (
            case_dir
            for case_dir in zero_cases
            if (case_dir / f"{case_dir.name}_doe_fixed_cl.csv").exists()
        ),
        None,
    )
    if source is None:
        return
    with (source / f"{source.name}_doe_fixed_cl.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        source_row = next(csv.DictReader(handle))
    with (source / f"{source.name}_doe_alpha_points.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        alpha_rows = list(csv.DictReader(handle))
    for case_dir in zero_cases:
        result_path = case_dir / f"{case_dir.name}_doe_fixed_cl.csv"
        if result_path.exists():
            continue
        design = json.loads(
            (case_dir / f"{case_dir.name}_design.json").read_text(encoding="utf-8")
        )
        row = dict(source_row)
        row.update({
            "case_id": case_dir.name,
            "x_h_over_c": design["x_h_over_c"],
            "shape_type": design["shape_type"],
            "evaluation_method": f"copied zero-amplitude result from {source.name}",
        })
        write_csv(result_path, [row])
        write_csv(case_dir / f"{case_dir.name}_doe_alpha_points.csv", alpha_rows)


def main():
    args = parse_args()
    if args.worker:
        worker(args)
        return
    root = args.project / "outputs" / "doe"
    case_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    pending = [
        path
        for path in case_dirs
        if args.force or not (path / f"{path.name}_doe_fixed_cl.csv").exists()
    ]
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"DOE runner: pending={len(pending)}, workers={args.workers}")
    failed = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(launch_case, args, path): path for path in pending}
        for future in as_completed(futures):
            path = futures[future]
            try:
                print(f"complete: {future.result()}")
            except Exception as exc:
                failed.append({"case_id": path.name, "reason": str(exc)})
                print(f"failed: {path.name}: {exc}")
    if failed and args.workers > 1:
        retry_failed = []
        print(f"Serial retry for {len(failed)} parallel failures")
        for failure in failed:
            path = root / failure["case_id"]
            try:
                print(f"retry complete: {launch_case(args, path)}")
            except Exception as exc:
                retry_failed.append({"case_id": path.name, "reason": str(exc)})
                print(f"retry failed: {path.name}: {exc}")
        failed = retry_failed
    fill_zero_amplitude_duplicates(args.project)
    complete_count, missing_count = aggregate(args.project)
    print(
        f"DOE status: complete={complete_count}, missing={missing_count}, "
        f"failed_this_run={len(failed)}"
    )
    if failed:
        raise RuntimeError(f"{len(failed)} DOE cases failed")


if __name__ == "__main__":
    main()


