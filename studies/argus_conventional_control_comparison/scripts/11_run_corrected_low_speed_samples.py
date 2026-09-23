from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")
DEFAULT_PYTHON = Path(r"<OPENVSP_PYTHON>")
FT_TO_M = 0.3048
SLUG_FT3_TO_KG_M3 = 515.3788184


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--trim-mode",
        choices=["fast", "iterative"],
        default="fast",
        help=(
            "fast: one multi-alpha sweep plus one final load solve; "
            "iterative: legacy repeated single-alpha secant solves"
        ),
    )
    parser.add_argument("--alpha-low", type=float, default=1.0)
    parser.add_argument("--alpha-high", type=float, default=2.5)
    parser.add_argument("--alpha-points", type=int, default=2)
    parser.add_argument(
        "--cl-tolerance",
        type=float,
        default=2.0e-4,
        help=(
            "Search-stage CL tolerance. Use 2e-4 for speed; use 2e-5 or "
            "--trim-mode iterative for final verification."
        ),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case-dir", type=Path)
    parser.add_argument(
        "--optimization-root",
        type=Path,
        help="Independent corrected hinged sample/result root.",
    )
    parser.add_argument(
        "--optimization-config",
        type=Path,
        help="Corrected low-speed solver/constraint config.",
    )
    parser.add_argument(
        "--baseline-config",
        type=Path,
        help="Audited aerodynamic/unit config for the corrected baseline.",
    )
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
    raise RuntimeError(f"Missing result fields: {names}")


def write_csv(path, rows):
    fields = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
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


def evaluate(vsp, wing_id, alpha, mach, config, loads=False):
    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", config["reference_area_native"])
    set_double(vsp, analysis, "cref", config["reference_chord_native"])
    set_double(vsp, analysis, "bref", config["reference_span_native"])
    set_string(vsp, analysis, "WingID", wing_id)
    for prefix, value in [("Alpha", alpha), ("Beta", 0.0), ("Mach", mach)]:
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
    if not loads:
        return result, []
    load_id = vsp.FindLatestResultsID("VSPAERO_Load")
    names = list(vsp.GetAllDataNames(load_id))
    columns = {name: doubles(vsp, load_id, name) for name in names}
    count = max(len(values) for values in columns.values())
    rows = []
    for index in range(count):
        rows.append({name: values[index] for name, values in columns.items() if index < len(values)})
    return result, rows


def trim_iterative(vsp, wing_id, guess, cl_target, mach, config, tolerance):
    """Legacy robust trim using repeated single-alpha VSPAERO executions."""
    p0, _ = evaluate(vsp, wing_id, guess - 0.3, mach, config)
    p1, _ = evaluate(vsp, wing_id, guess + 0.3, mach, config)
    trace = [p0, p1]
    execution_count = 2
    for _ in range(5):
        alpha = p1["alpha_deg"] + (cl_target - p1["CL"]) * (
            p1["alpha_deg"] - p0["alpha_deg"]
        ) / (p1["CL"] - p0["CL"])
        point, _ = evaluate(vsp, wing_id, alpha, mach, config)
        execution_count += 1
        trace.append(point)
        if abs(point["CL"] - cl_target) <= tolerance:
            final, loads = evaluate(vsp, wing_id, alpha, mach, config, loads=True)
            execution_count += 1
            return final, loads, trace, execution_count
        p0, p1 = p1, point
    raise RuntimeError("Fixed-CL trim did not converge")


def sweep_points(vsp, wing_id, alphas, mach, config):
    """Evaluate several angles in one VSPAERO process and reuse its setup."""
    analysis = "VSPAEROSweep"
    count_before = vsp.GetNumResults("VSPAERO_History")
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", config["reference_area_native"])
    set_double(vsp, analysis, "cref", config["reference_chord_native"])
    set_double(vsp, analysis, "bref", config["reference_span_native"])
    set_string(vsp, analysis, "WingID", wing_id)
    set_double(vsp, analysis, "AlphaStart", alphas[0])
    set_double(vsp, analysis, "AlphaEnd", alphas[-1])
    set_int(vsp, analysis, "AlphaNpts", len(alphas))
    set_double(vsp, analysis, "BetaStart", 0.0)
    set_double(vsp, analysis, "BetaEnd", 0.0)
    set_int(vsp, analysis, "BetaNpts", 1)
    set_double(vsp, analysis, "MachStart", mach)
    set_double(vsp, analysis, "MachEnd", mach)
    set_int(vsp, analysis, "MachNpts", 1)
    set_int(vsp, analysis, "WakeNumIter", config["wake_iterations"])
    vsp.ExecAnalysis(analysis)
    count_after = vsp.GetNumResults("VSPAERO_History")
    created = count_after - count_before
    if created < len(alphas):
        raise RuntimeError(
            f"Expected {len(alphas)} sweep results, VSPAERO created {created}"
        )
    result_ids = [
        vsp.FindResultsID("VSPAERO_History", index)
        for index in range(count_after - len(alphas), count_after)
    ]
    return [
        {
            "alpha_deg": alpha,
            "CL": last(vsp, result_id, ["CLtot", "CL"]),
            "CD": last(vsp, result_id, ["CDtot", "CD"]),
            "CDi": last(vsp, result_id, ["CDi"]),
            "Cm": last(vsp, result_id, ["CMytot", "CMy", "Cm"]),
        }
        for alpha, result_id in zip(alphas, result_ids)
    ]


def interpolate_alpha(points, cl_target):
    """Interpolate alpha from the two sweep points bracketing target CL."""
    ordered = sorted(points, key=lambda row: row["CL"])
    if cl_target <= ordered[0]["CL"]:
        left, right = ordered[0], ordered[1]
    elif cl_target >= ordered[-1]["CL"]:
        left, right = ordered[-2], ordered[-1]
    else:
        right_index = next(
            index for index, row in enumerate(ordered) if row["CL"] >= cl_target
        )
        left, right = ordered[right_index - 1], ordered[right_index]
    slope = (right["CL"] - left["CL"]) / (
        right["alpha_deg"] - left["alpha_deg"]
    )
    if abs(slope) < 1.0e-10:
        raise RuntimeError("Near-zero lift-curve slope in fast trim")
    alpha = left["alpha_deg"] + (cl_target - left["CL"]) / slope
    return alpha, slope


def trim_fast(
    vsp,
    wing_id,
    cl_target,
    mach,
    config,
    alpha_low,
    alpha_high,
    alpha_points,
    tolerance,
):
    """Two-stage trim: one multi-alpha sweep, then one exact load solve.

    A correction solve is only added when the final CL misses the requested
    tolerance. For this VLM model CL(alpha) is nearly linear, so two VSPAERO
    executions are normally sufficient.
    """
    if alpha_points < 2:
        raise ValueError("alpha_points must be at least 2")
    step = (alpha_high - alpha_low) / (alpha_points - 1)
    alphas = [alpha_low + index * step for index in range(alpha_points)]
    trace = sweep_points(vsp, wing_id, alphas, mach, config)
    alpha, slope = interpolate_alpha(trace, cl_target)
    final, loads = evaluate(vsp, wing_id, alpha, mach, config, loads=True)
    trace.append(final)
    execution_count = 2
    if abs(final["CL"] - cl_target) > tolerance:
        corrected_alpha = alpha + (cl_target - final["CL"]) / slope
        final, loads = evaluate(
            vsp, wing_id, corrected_alpha, mach, config, loads=True
        )
        trace.append(final)
        execution_count += 1
    return final, loads, trace, execution_count


def collapse_spanwise_loads(raw, design, config):
    """Convert native OpenVSP strip geometry to audited SI sectional loads.

    The NASA EET model is stored in feet. Earlier versions treated native
    Chord, dSpan, and Yavg values as metres, which corrupted every dimensional
    load and moment while leaving dimensionless coefficients unchanged.
    """
    length_to_m = float(config["native_length_to_m"])
    rho = float(config["load_condition_rho_kg_m3"])
    velocity = float(config["load_condition_velocity_m_s"])
    q = 0.5 * rho * velocity**2
    semi_span_native = 0.5 * float(config["reference_span_native"])
    bins = {}
    for row in raw:
        bins.setdefault(round(abs(float(row.get("Yavg", 0.0))), 8), []).append(row)
    strips = []
    for y_native, items in sorted(bins.items()):
        avg = lambda name: sum(float(item.get(name, 0.0)) for item in items) / len(items)
        chord_native = avg("Chord")
        dy_native = avg("dSpan")
        chord_m = chord_native * length_to_m
        dy_m = dy_native * length_to_m
        y_m = y_native * length_to_m
        cl = avg("cl")
        cd = avg("cd")
        cdi = avg("cdi")
        eta = y_native / semi_span_native
        lift_per_span = q * chord_m * cl
        drag_per_span = q * chord_m * cd
        induced_drag_per_span = q * chord_m * cdi
        strips.append({
            "eta": eta,
            "y_native_ft": y_native,
            "dy_native_ft": dy_native,
            "chord_native_ft": chord_native,
            "y_m": y_m,
            "dy_m": dy_m,
            "chord_m": chord_m,
            "sectional_cl": cl,
            "sectional_cd": cd,
            "sectional_cdi": cdi,
            "lift_per_span_N_per_m": lift_per_span,
            "drag_per_span_N_per_m": drag_per_span,
            "induced_drag_per_span_N_per_m": induced_drag_per_span,
            "sectional_cmy_native": avg("cmy"),
            "morph_region": (
                float(design["eta_start"]) <= eta <= float(design["eta_end"])
            ),
        })
    return strips


def load_metrics(strips, design, config):
    root_bending = sum(
        row["lift_per_span_N_per_m"] * row["dy_m"] * row["y_m"] for row in strips
    )
    morph = [
        row for row in strips
        if float(design["eta_start"]) <= row["eta"] <= float(design["eta_end"])
    ]
    morph_lift = sum(row["lift_per_span_N_per_m"] * row["dy_m"] for row in morph)
    return root_bending, morph_lift


def legacy_to_audited_moment_scale(config):
    """Scale legacy q*L^3 moments to the audited SI condition.

    This is used only to convert the historical baseline value needed for the
    relative root-bending constraint. Candidate loads themselves are rebuilt
    directly from native VSPAERO strips by ``collapse_spanwise_loads``.
    """
    legacy_q = 0.5 * float(config["legacy_rho_kg_m3"]) * float(
        config["legacy_velocity_m_s"]
    ) ** 2
    audited_q = 0.5 * float(config["load_condition_rho_kg_m3"]) * float(
        config["load_condition_velocity_m_s"]
    ) ** 2
    return audited_q / legacy_q * float(config["native_length_to_m"]) ** 3


def worker(args):
    started = time.perf_counter()
    project = args.project.resolve()
    case_dir = args.case_dir.resolve()
    case_id = case_dir.name
    result_path = case_dir / f"{case_id}_optimization_result.csv"
    if result_path.exists() and not args.force:
        return
    baseline_config_path = args.baseline_config or (
        project / "config" / "corrected_baseline_config.json"
    )
    if not baseline_config_path.is_absolute():
        baseline_config_path = project / baseline_config_path
    config = json.loads(baseline_config_path.read_text(encoding="utf-8"))
    config_path = args.optimization_config or (
        project / "config" / "corrected_low_speed_solver_config.json"
    )
    if not config_path.is_absolute():
        config_path = project / config_path
    opt_config = json.loads(config_path.read_text(encoding="utf-8"))
    design = json.loads((case_dir / f"{case_id}_design.json").read_text())
    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(case_dir / f"{case_id}.vsp3"))
    vsp.Update()
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    configure_geometry(vsp, config)
    if args.trim_mode == "fast":
        final, loads, trace, execution_count = trim_fast(
            vsp,
            wing_id,
            opt_config["cl_target"],
            design["mach"],
            config,
            args.alpha_low,
            args.alpha_high,
            args.alpha_points,
            args.cl_tolerance,
        )
    else:
        final, loads, trace, execution_count = trim_iterative(
            vsp,
            wing_id,
            1.6,
            opt_config["cl_target"],
            design["mach"],
            config,
            args.cl_tolerance,
        )
    spanwise_loads = collapse_spanwise_loads(loads, design, config)
    root_bending, morph_lift = load_metrics(spanwise_loads, design, config)
    if "baseline_root_bending_moment_Nm" in opt_config:
        baseline_bending = float(opt_config["baseline_root_bending_moment_Nm"])
    else:
        baseline = next(
            row for row in csv.DictReader(
                (
                    project
                    / "outputs"
                    / "exact_trim_loads"
                    / "exact_trim_load_summary.csv"
                ).open(encoding="utf-8-sig")
            )
            if row["case_id"] == "refined_baseline"
        )
        baseline_bending = (
            float(baseline["half_wing_root_bending_moment_Nm"])
            * legacy_to_audited_moment_scale(config)
        )
    bending_increase = 100.0 * (
        root_bending - baseline_bending
    ) / baseline_bending
    deflections = [float(value) for value in design["segment_deflections_deg"]]
    lower, upper = [
        float(value) for value in opt_config["deflection_bounds_deg"]
    ]
    row = {
        "case_id": case_id,
        "delta_inboard_deg": deflections[0],
        "delta_outboard_deg": deflections[1],
        "alpha_trim_deg": final["alpha_deg"],
        "CL": final["CL"],
        "CL_error": final["CL"] - opt_config["cl_target"],
        "CD": final["CD"],
        "CDi": final["CDi"],
        "Cm": final["Cm"],
        "root_bending_moment_Nm": root_bending,
        "root_bending_increase_percent": bending_increase,
        "morph_region_lift_N": morph_lift,
        "segment_jump_deg": abs(deflections[1] - deflections[0]),
        "max_abs_deflection_deg": max(abs(value) for value in deflections),
        "hinge_x_over_c": design["hinge_x_over_c"],
        "dimensional_load_audit": "SI_from_native_ft_geometry",
        "hinge_moment_status": "not_computed_requires_surface_pressure_integration",
        "trim_mode": args.trim_mode,
        "vspaero_execution_count": execution_count,
        "evaluation_seconds": time.perf_counter() - started,
        "feasible": (
            bending_increase
            <= opt_config["root_bending_increase_limit_percent"]
            and all(lower <= value <= upper for value in deflections)
        ),
    }
    write_csv(result_path, [row])
    write_csv(case_dir / f"{case_id}_trim_trace.csv", trace)
    write_csv(case_dir / f"{case_id}_spanwise_loads.csv", spanwise_loads)


def launch(args, case_dir, attempt="parallel"):
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
        "--trim-mode",
        args.trim_mode,
        "--alpha-low",
        str(args.alpha_low),
        "--alpha-high",
        str(args.alpha_high),
        "--alpha-points",
        str(args.alpha_points),
        "--cl-tolerance",
        str(args.cl_tolerance),
    ]
    if args.optimization_root:
        command.extend(["--optimization-root", str(args.optimization_root.resolve())])
    if args.optimization_config:
        config_path = args.optimization_config
        if not config_path.is_absolute():
            config_path = args.project.resolve() / config_path
        command.extend(["--optimization-config", str(config_path.resolve())])
    if args.baseline_config:
        baseline_config_path = args.baseline_config
        if not baseline_config_path.is_absolute():
            baseline_config_path = args.project.resolve() / baseline_config_path
        command.extend(["--baseline-config", str(baseline_config_path.resolve())])
    if args.force:
        command.append("--force")
    # OpenVSP/VSPAERO can create auxiliary files in both the process working
    # directory and the Windows temporary directory. Isolate both locations
    # so independent candidates do not race over shared files.
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
    log_path = case_dir / f"{case_dir.name}_optimization.log"
    log_path.write_text(
        completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8"
    )
    if completed.returncode:
        (case_dir / f"{case_dir.name}_{attempt}_failure.log").write_text(
            completed.stdout + "\nSTDERR\n" + completed.stderr,
            encoding="utf-8",
        )
        raise RuntimeError(f"{case_dir.name} failed")
    return case_dir.name


def aggregate(project, optimization_root=None):
    rows = []
    root = optimization_root or project / "outputs" / "optimization"
    root = root.resolve()
    samples_root = root / "samples"
    for case_dir in sorted(path for path in samples_root.iterdir() if path.is_dir()):
        result = case_dir / f"{case_dir.name}_optimization_result.csv"
        if result.exists():
            with result.open(newline="", encoding="utf-8-sig") as handle:
                rows.append(next(csv.DictReader(handle)))
    if rows:
        write_csv(
            root / "optimization_samples.csv",
            rows,
        )
    return len(rows)


def main():
    args = parse_args()
    if args.worker:
        worker(args)
        return
    optimization_root = args.optimization_root or (
        args.project / "outputs" / "optimization"
    )
    if not optimization_root.is_absolute():
        optimization_root = args.project / optimization_root
    root = optimization_root / "samples"
    pending = [
        path for path in sorted(root.iterdir()) if path.is_dir()
        and (args.force or not (path / f"{path.name}_optimization_result.csv").exists())
    ]
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(launch, args, path, "parallel"): path
            for path in pending
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                print(f"complete: {future.result()}")
            except Exception as exc:
                failures.append(path)
                print(f"failed: {path.name}: {exc}")
    if failures and args.workers > 1:
        print(f"Serial retry: {len(failures)}")
        retry = []
        for path in failures:
            try:
                print(f"retry complete: {launch(args, path, 'serial_retry')}")
            except Exception:
                retry.append(path)
        failures = retry
    count = aggregate(args.project, optimization_root)
    print(f"Optimization samples complete={count}, failed={len(failures)}")
    if failures:
        raise RuntimeError(f"{len(failures)} samples failed")


if __name__ == "__main__":
    main()


