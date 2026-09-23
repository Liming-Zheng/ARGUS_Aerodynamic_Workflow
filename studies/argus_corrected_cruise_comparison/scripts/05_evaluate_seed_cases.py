"""Evaluate all morphing seed geometries at early and late cruise in parallel."""

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
    parser.add_argument("--workers", type=int)
    parser.add_argument("--case-root", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument(
        "--concept",
        choices=["all", "trailing_edge", "twist"],
        default="all",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--consolidate-only",
        action="store_true",
        help="Rebuild aggregate CSV/JSON files from completed case summaries.",
    )
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


def read_csv_row(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        return next(csv.DictReader(handle))


def evaluate_worker(args: argparse.Namespace) -> None:
    project = args.project.resolve()
    case_dir = args.case_dir.resolve()
    case_id = case_dir.name
    output = case_dir / "evaluation"
    summary_path = output / f"{case_id}_state_summary.csv"
    if summary_path.exists() and not args.force:
        return
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(project / "src"))

    from argus_cruise_comparison.constraints import constraint_status
    from argus_cruise_comparison.vspaero import (
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
        (
            project
            / "outputs"
            / "study_definition"
            / "flight_states.json"
        ).read_text(encoding="utf-8")
    )
    scale = json.loads(
        (
            project
            / "outputs"
            / "study_definition"
            / "scale_definition.json"
        ).read_text(encoding="utf-8")
    )
    constraint_definition = json.loads(
        (
            project
            / "outputs"
            / "rigid_baseline"
            / "constraint_definition.json"
        ).read_text(encoding="utf-8")
    )
    design = json.loads(
        (case_dir / f"{case_id}_design.json").read_text(encoding="utf-8")
    )
    model = case_dir / f"{case_id}.vsp3"
    morph = config["morphing"]
    analysis = config["aerodynamic_analysis"]
    if design["concept"] == "trailing_edge":
        concept_config = morph["trailing_edge"]
        amplitude_limit = max(
            abs(value)
            for value in concept_config["amplitude_bounds_over_c"]
        )
        adjacent_limit = concept_config[
            "max_adjacent_control_delta_over_c"
        ]
    else:
        concept_config = morph["twist"]
        amplitude_limit = max(
            abs(value) for value in concept_config["twist_bounds_deg"]
        )
        adjacent_limit = concept_config["max_adjacent_control_delta_deg"]

    vsp = load_vsp(Path(config["runtime"]["openvsp_root"]))
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(model))
    vsp.Update()
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    if not wing_id:
        raise RuntimeError(f"Wing geometry not found: {config['wing_name']}")
    configure_geometry(vsp, analysis)

    rows: list[dict] = []
    for state in states:
        started = time.perf_counter()
        final, raw_loads, trace, execution_count = trim_to_cl(
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
            morph_eta_start=morph["eta_start"],
            morph_eta_end=morph["eta_end"],
            moment_axis_x_over_c=(
                design.get("x_h_over_c")
                or design.get("rotation_axis_x_over_c")
                or 0.25
            ),
        )
        metrics = integrate_load_metrics(strips)
        schedule_metrics = design["schedule_metrics"]
        constraints = constraint_status(
            root_bending_moment_Nm=metrics[
                "half_wing_root_bending_moment_Nm"
            ],
            root_bending_limit_Nm=constraint_definition[
                "root_bending_limit_Nm"
            ],
            max_abs_command=schedule_metrics["max_abs_value_dense"],
            max_abs_command_limit=amplitude_limit,
            max_adjacent_delta=schedule_metrics[
                "max_adjacent_control_delta"
            ],
            max_adjacent_delta_limit=adjacent_limit,
            relative_tolerance=analysis["constraint_relative_tolerance"],
        )
        constraint_rows = {
            item["name"]: item for item in constraints["constraints"]
        }
        state_dir = output / state["name"]
        write_csv(state_dir / "trim_trace.csv", trace)
        write_csv(state_dir / "spanwise_loads.csv", strips)
        row = {
            "case_id": case_id,
            "concept": design["concept"],
            "flight_state": state["name"],
            **{
                f"u{index + 1}": value
                for index, value in enumerate(design["control_values"])
            },
            "tip_value": schedule_metrics["tip_value"],
            "max_abs_command": schedule_metrics["max_abs_value_dense"],
            "max_adjacent_control_delta": schedule_metrics[
                "max_adjacent_control_delta"
            ],
            "target_lift_N": state["target_lift_N"],
            "target_CL": state["target_CL"],
            "alpha_trim_deg": final["alpha_deg"],
            "CL": final["CL"],
            "CL_error": final["CL"] - state["target_CL"],
            "CD": final["CD"],
            "CDi": final["CDi"],
            "Cm": final["Cm"],
            **metrics,
            "root_bending_limit_Nm": constraint_definition[
                "root_bending_limit_Nm"
            ],
            "root_bending_utilization": constraint_rows[
                "absolute_root_bending"
            ]["utilization"],
            "root_bending_active": constraint_rows[
                "absolute_root_bending"
            ]["active"],
            "feasible": constraints["feasible"],
            "active_constraints": ";".join(
                constraints["active_constraints"]
            ),
            "vspaero_execution_count": execution_count,
            "evaluation_seconds": time.perf_counter() - started,
        }
        rows.append(row)
    write_csv(summary_path, rows)


def discover_cases(root: Path, concept: str) -> list[Path]:
    cases = [
        path.parent
        for path in root.glob("*/*_design.json")
        if concept == "all"
        or json.loads(path.read_text(encoding="utf-8"))["concept"] == concept
    ]
    return sorted(set(cases))


def run_case(
    python_executable: Path,
    script: Path,
    project: Path,
    case_dir: Path,
    force: bool,
) -> tuple[str, bool, str]:
    command = [
        str(python_executable),
        str(script),
        "--worker",
        "--project",
        str(project),
        "--case-dir",
        str(case_dir),
    ]
    if force:
        command.append("--force")
    log_path = case_dir / "evaluation.log"
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(
            command,
            cwd=case_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    message = "" if result.returncode == 0 else str(log_path)
    return case_dir.name, result.returncode == 0, message


def consolidate(project: Path, cases: list[Path], output_path: Path) -> None:
    sys.path.insert(0, str(project / "src"))
    from argus_cruise_comparison.vspaero import write_csv

    rows: list[dict] = []
    for case_dir in cases:
        summary = (
            case_dir
            / "evaluation"
            / f"{case_dir.name}_state_summary.csv"
        )
        if summary.exists():
            with summary.open(encoding="utf-8-sig") as handle:
                rows.extend(csv.DictReader(handle))
    write_csv(output_path, rows)


def main() -> None:
    args = parse_args()
    if args.worker:
        if args.case_dir is None:
            raise ValueError("--case-dir is required in worker mode")
        evaluate_worker(args)
        return

    project = args.project.resolve()
    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    workers = args.workers or int(config["runtime"]["workers"])
    case_root = (
        args.case_root.resolve()
        if args.case_root is not None
        else project / "outputs" / "seed_cases"
    )
    summary_output = (
        args.summary_output.resolve()
        if args.summary_output is not None
        else project / "outputs" / "seed_evaluations" / "all_seed_results.csv"
    )
    cases = discover_cases(case_root, args.concept)
    python_executable = Path(config["runtime"]["openvsp_python"])
    script = Path(__file__).resolve()
    failures: list[dict] = []
    completed = 0
    started = time.perf_counter()

    if args.consolidate_only:
        consolidate(project, cases, summary_output)
        failure_path = summary_output.with_name(
            f"{summary_output.stem}_failures.json"
        )
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text("[]\n", encoding="utf-8")
        print(f"Consolidated {len(cases)} completed case directories")
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                run_case,
                python_executable,
                script,
                project,
                case_dir,
                args.force,
            ): case_dir
            for case_dir in cases
        }
        for future in as_completed(futures):
            case_id, success, message = future.result()
            completed += 1
            if not success:
                failures.append({"case_id": case_id, "log": message})
            print(
                f"[{completed:02d}/{len(cases):02d}] "
                f"{case_id}: {'ok' if success else 'FAILED'}"
            )

    if failures and workers > 1:
        failed_ids = {item["case_id"] for item in failures}
        retry_failures: list[dict] = []
        print(f"Serial retry for {len(failed_ids)} parallel failures")
        for index, case_dir in enumerate(
            (path for path in cases if path.name in failed_ids),
            start=1,
        ):
            case_id, success, message = run_case(
                python_executable,
                script,
                project,
                case_dir,
                args.force,
            )
            print(
                f"[retry {index:02d}/{len(failed_ids):02d}] "
                f"{case_id}: {'ok' if success else 'FAILED'}"
            )
            if not success:
                retry_failures.append({"case_id": case_id, "log": message})
        failures = retry_failures

    consolidate(project, cases, summary_output)
    failure_path = summary_output.with_name(
        f"{summary_output.stem}_failures.json"
    )
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(
        json.dumps(failures, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Finished {len(cases)} cases with {len(failures)} failures in "
        f"{time.perf_counter() - started:.1f} s"
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

