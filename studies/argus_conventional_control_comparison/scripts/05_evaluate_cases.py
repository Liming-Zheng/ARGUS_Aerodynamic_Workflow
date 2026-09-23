"""Strict fixed-lift VSPAERO evaluation of conventional-control cases."""

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


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case-dir", type=Path)
    return parser.parse_args()


def load_vsp(openvsp_root: Path):
    os.add_dll_directory(str(openvsp_root))
    os.add_dll_directory(str(openvsp_root / "python" / "openvsp" / "openvsp"))
    for relative in [
        "python/openvsp",
        "python/openvsp_config",
        "python/degen_geom",
        "python/utilities",
    ]:
        sys.path.insert(0, str(openvsp_root / relative))
    import openvsp as vsp
    return vsp


def worker(args: argparse.Namespace) -> None:
    project = args.project.resolve()
    case_dir = args.case_dir.resolve()
    case_id = case_dir.name
    output = case_dir / "evaluation"
    summary_path = output / f"{case_id}_state_summary.csv"
    if summary_path.exists() and not args.force:
        return
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(project / "src"))
    from argus_conventional_control.constraints import constraint_status
    from argus_conventional_control.vspaero import (
        collapse_spanwise_loads,
        configure_geometry,
        integrate_load_metrics,
        trim_to_cl,
        write_csv,
    )

    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    states = json.loads(
        (project / "outputs" / "study_definition" / "flight_states.json").read_text(encoding="utf-8")
    )
    scale = json.loads(
        (project / "outputs" / "study_definition" / "scale_definition.json").read_text(encoding="utf-8")
    )
    root_limit = float(
        json.loads(
            (project / "outputs" / "rigid_baseline" / "constraint_definition.json").read_text(encoding="utf-8")
        )["root_bending_limit_Nm"]
    )
    design = json.loads(
        (case_dir / f"{case_id}_design.json").read_text(encoding="utf-8")
    )
    model = case_dir / f"{case_id}.vsp3"
    settings = config["conventional_control"]
    bound = max(abs(float(value)) for value in settings["optimization_deflection_bounds_deg"])
    analysis = config["aerodynamic_analysis"]
    vsp = load_vsp(Path(config["runtime"]["openvsp_root"]))
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(model))
    vsp.Update()
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    configure_geometry(vsp, analysis)
    rows = []
    for state in states:
        started = time.perf_counter()
        final, raw_loads, trace, executions = trim_to_cl(
            vsp,
            wing_id,
            state["target_CL"],
            state["mach"],
            config["native_geometry"],
            analysis,
            alpha_low=0.0,
            alpha_high=4.0,
            tolerance=analysis["strict_cl_tolerance"],
        )
        strips = collapse_spanwise_loads(
            raw_loads,
            state,
            scale,
            config["native_geometry"],
            morph_eta_start=float(config["morphing"]["eta_start"]),
            morph_eta_end=float(config["morphing"]["eta_end"]),
            moment_axis_x_over_c=float(settings["hinge_x_over_c"]),
        )
        metrics = integrate_load_metrics(strips)
        commands = [float(value) for value in design["segment_deflections_deg"]]
        status = constraint_status(
            root_bending_moment_Nm=metrics["half_wing_root_bending_moment_Nm"],
            root_bending_limit_Nm=root_limit,
            max_abs_command=max(abs(value) for value in commands),
            max_abs_command_limit=bound,
            max_adjacent_delta=0.0,
            max_adjacent_delta_limit=1.0e9,
            relative_tolerance=analysis["constraint_relative_tolerance"],
        )
        by_name = {item["name"]: item for item in status["constraints"]}
        state_dir = output / state["name"]
        write_csv(state_dir / "trim_trace.csv", trace)
        write_csv(state_dir / "spanwise_loads.csv", strips)
        rows.append(
            {
                "case_id": case_id,
                "concept": "conventional_hinged",
                "flight_state": state["name"],
                "delta_inboard_deg": commands[0],
                "delta_outboard_deg": commands[1],
                "segment_jump_deg": abs(commands[1] - commands[0]),
                "max_abs_deflection_deg": max(abs(value) for value in commands),
                "target_lift_N": state["target_lift_N"],
                "target_CL": state["target_CL"],
                "alpha_trim_deg": final["alpha_deg"],
                "CL": final["CL"],
                "CL_error": final["CL"] - state["target_CL"],
                "CD": final["CD"],
                "CDi": final["CDi"],
                "Cm": final["Cm"],
                **metrics,
                "root_bending_limit_Nm": root_limit,
                "root_bending_utilization": by_name["absolute_root_bending"]["utilization"],
                "root_bending_active": by_name["absolute_root_bending"]["active"],
                "feasible": status["feasible"],
                "active_constraints": ";".join(status["active_constraints"]),
                "vspaero_execution_count": executions,
                "evaluation_seconds": time.perf_counter() - started,
            }
        )
    write_csv(summary_path, rows)


def run_case(python: Path, script: Path, project: Path, case_dir: Path, force: bool):
    command = [str(python), str(script), "--worker", "--project", str(project), "--case-dir", str(case_dir)]
    if force:
        command.append("--force")
    log_path = case_dir / "evaluation.log"
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=case_dir, stdout=log, stderr=subprocess.STDOUT, text=True, check=False)
    return case_dir.name, result.returncode == 0, str(log_path)


def consolidate(project: Path, cases: list[Path], batch: int) -> None:
    sys.path.insert(0, str(project / "src"))
    from argus_conventional_control.vspaero import write_csv
    rows = []
    for case_dir in cases:
        path = case_dir / "evaluation" / f"{case_dir.name}_state_summary.csv"
        if path.exists():
            with path.open(encoding="utf-8-sig") as handle:
                rows.extend(csv.DictReader(handle))
    write_csv(project / "outputs" / "evaluations" / f"batch_{batch:02d}_results.csv", rows)


def main() -> None:
    args = parse_args()
    if args.worker:
        worker(args)
        return
    project = args.project.resolve()
    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    root = project / "outputs" / "cases" / f"batch_{args.batch:02d}"
    cases = sorted(path.parent for path in root.glob("*/*_design.json"))
    workers = args.workers or int(config["runtime"]["workers"])
    python = Path(config["runtime"]["openvsp_python"])
    script = Path(__file__).resolve()
    failures = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_case, python, script, project, case, args.force): case
            for case in cases
        }
        for index, future in enumerate(as_completed(futures), start=1):
            case_id, ok, log = future.result()
            print(f"[{index:02d}/{len(cases):02d}] {case_id}: {'ok' if ok else 'FAILED'}")
            if not ok:
                failures.append((case_id, log))
    if failures and workers > 1:
        retry = []
        failed_ids = {item[0] for item in failures}
        for case in cases:
            if case.name in failed_ids:
                case_id, ok, log = run_case(python, script, project, case, args.force)
                print(f"[retry] {case_id}: {'ok' if ok else 'FAILED'}")
                if not ok:
                    retry.append((case_id, log))
        failures = retry
    consolidate(project, cases, args.batch)
    print(f"Finished in {time.perf_counter() - started:.1f} s with {len(failures)} failures")
    if failures:
        raise SystemExit(f"Failed cases: {failures}")


if __name__ == "__main__":
    main()

