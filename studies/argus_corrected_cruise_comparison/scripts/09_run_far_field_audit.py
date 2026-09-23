"""Re-evaluate corrected cruise geometries with explicit far-field outputs.

The audit is non-destructive: every source ``.vsp3`` is copied into an
independent working directory before VSPAERO is called. Native files are copied
after each flight state so the early-cruise files cannot be overwritten by the
late-cruise run.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


NATIVE_SUFFIXES = [".polar", ".lod", ".history", ".vspaero"]
CONCEPTS = ["rigid", "conventional_hinged", "trailing_edge", "twist"]
AUDIT_SCHEMA_VERSION = 2


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--concept", choices=["all", *CONCEPTS], default="all")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--consolidate-only", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case-dir", type=Path)
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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


def source_records(project: Path) -> list[dict]:
    records = [
        {
            "case_id": "rigid_baseline",
            "concept": "rigid",
            "model": str(
                project
                / "outputs"
                / "rigid_baseline"
                / "model"
                / "rigid_baseline.vsp3"
            ),
            "design": "",
            "schedule": "",
        }
    ]
    continuous_roots = [
        project / "outputs" / "seed_cases",
        project / "outputs" / "optimization_cases",
        project / "outputs" / "far_field_optimization" / "cases",
    ]
    for root in continuous_roots:
        for design_path in sorted(root.rglob("*_design.json")):
            design = json.loads(design_path.read_text(encoding="utf-8"))
            case_id = design["case_id"]
            model = design_path.parent / f"{case_id}.vsp3"
            schedule = design_path.parent / f"{case_id}_section_schedule.csv"
            records.append(
                {
                    "case_id": case_id,
                    "concept": design["concept"],
                    "model": str(model),
                    "design": str(design_path),
                    "schedule": str(schedule) if schedule.exists() else "",
                }
            )
    conventional = project.parent / "argus_corrected_conventional_cruise"
    for design_path in sorted(
        (conventional / "outputs" / "cases").rglob("*_design.json")
    ):
        design = json.loads(design_path.read_text(encoding="utf-8"))
        case_id = design["case_id"]
        model = design_path.parent / f"{case_id}.vsp3"
        schedule = design_path.parent / f"{case_id}_section_schedule.csv"
        records.append(
            {
                "case_id": case_id,
                "concept": "conventional_hinged",
                "model": str(model),
                "design": str(design_path),
                "schedule": str(schedule) if schedule.exists() else "",
            }
        )
    seen: set[str] = set()
    for record in records:
        case_id = record["case_id"]
        if case_id in seen:
            raise RuntimeError(f"Duplicate far-field audit case: {case_id}")
        seen.add(case_id)
        if not Path(record["model"]).exists():
            raise FileNotFoundError(record["model"])
    return records


def selected_records(records: list[dict], args: argparse.Namespace) -> list[dict]:
    requested = set(args.case_id)
    return [
        record
        for record in records
        if (args.concept == "all" or record["concept"] == args.concept)
        and (not requested or record["case_id"] in requested)
    ]


def prepare_cases(project: Path, records: list[dict]) -> list[Path]:
    root = project / "outputs" / "far_field_audit" / "cases"
    case_dirs: list[Path] = []
    for record in records:
        case_dir = root / record["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record["model"], case_dir / f"{record['case_id']}.vsp3")
        metadata = dict(record)
        metadata["source_model"] = metadata.pop("model")
        metadata["working_model"] = str(case_dir / f"{record['case_id']}.vsp3")
        (case_dir / "audit_case.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        if record["design"]:
            shutil.copy2(record["design"], case_dir / "source_design.json")
        if record["schedule"]:
            shutil.copy2(record["schedule"], case_dir / "section_schedule.csv")
        case_dirs.append(case_dir)
    write_csv(
        project / "outputs" / "far_field_audit" / "case_manifest.csv", records
    )
    return case_dirs


def preserve_native_files(case_dir: Path, state_dir: Path, case_id: str) -> None:
    native = state_dir / "native"
    native.mkdir(parents=True, exist_ok=True)
    for suffix in NATIVE_SUFFIXES:
        source = case_dir / f"{case_id}{suffix}"
        if not source.exists():
            raise FileNotFoundError(f"Missing VSPAERO native output: {source}")
        shutil.copy2(source, native / source.name)


def concept_region(design: dict) -> tuple[float, float, float]:
    concept = design["concept"]
    if concept == "conventional_hinged":
        return 0.71, 0.97, float(design.get("hinge_x_over_c", 0.70))
    if concept == "trailing_edge":
        return 0.60, 1.00, float(design.get("x_h_over_c", 0.62))
    if concept == "twist":
        return 0.60, 1.00, float(design.get("rotation_axis_x_over_c", 0.25))
    return 0.60, 1.00, 0.25


def evaluate_worker(args: argparse.Namespace) -> None:
    project = args.project.resolve()
    case_dir = args.case_dir.resolve()
    case_id = case_dir.name
    complete = case_dir / "audit_complete.json"
    if complete.exists() and not args.force:
        completion = json.loads(complete.read_text(encoding="utf-8"))
        if completion.get("audit_schema_version") == AUDIT_SCHEMA_VERSION:
            return
        summary_path = case_dir / "state_summary.csv"
        if summary_path.exists():
            header = summary_path.open(encoding="utf-8-sig").readline().split(",")
            if "e_far_field_total_CL" in header:
                return
    metadata = json.loads((case_dir / "audit_case.json").read_text(encoding="utf-8"))
    design_path = case_dir / "source_design.json"
    design = (
        json.loads(design_path.read_text(encoding="utf-8"))
        if design_path.exists()
        else {"case_id": case_id, "concept": metadata["concept"]}
    )
    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    states = json.loads(
        (project / "outputs" / "study_definition" / "flight_states.json").read_text(
            encoding="utf-8"
        )
    )
    scale = json.loads(
        (project / "outputs" / "study_definition" / "scale_definition.json").read_text(
            encoding="utf-8"
        )
    )
    aspect_ratio = float(scale["aircraft_reference_aspect_ratio"])
    root_limit = float(
        json.loads(
            (project / "outputs" / "rigid_baseline" / "constraint_definition.json").read_text(
                encoding="utf-8"
            )
        )["root_bending_limit_Nm"]
    )
    sys.path.insert(0, str(project / "src"))
    from argus_cruise_comparison.vspaero import (
        collapse_spanwise_loads,
        configure_geometry,
        integrate_load_metrics,
        trim_to_cl,
        write_csv as write_result_csv,
    )

    vsp = load_vsp(Path(config["runtime"]["openvsp_root"]))
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(case_dir / f"{case_id}.vsp3"))
    vsp.Update()
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    if not wing_id:
        raise RuntimeError(f"Wing geometry not found: {config['wing_name']}")
    analysis = config["aerodynamic_analysis"]
    configure_geometry(vsp, analysis)
    eta_start, eta_end, moment_axis = concept_region(design)
    summary: list[dict] = []
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
            morph_eta_start=eta_start,
            morph_eta_end=eta_end,
            moment_axis_x_over_c=moment_axis,
        )
        metrics = integrate_load_metrics(strips)
        state_dir = case_dir / state["name"]
        write_result_csv(state_dir / "trim_trace.csv", trace)
        write_result_csv(state_dir / "spanwise_loads.csv", strips)
        preserve_native_files(case_dir, state_dir, case_id)
        row = {
            "case_id": case_id,
            "concept": design["concept"],
            "flight_state": state["name"],
            "target_CL": state["target_CL"],
            "alpha_trim_deg": final["alpha_deg"],
            "CL": final["CL"],
            "CL_error": final["CL"] - state["target_CL"],
            "CD_total_near_field": final["CD"],
            "CDi_near_field": final["CDi_near_field"],
            "CDiw_far_field": final["CDiw_far_field"],
            # OpenVSP's API efficiencies use induced lift (CLi/CLiw).  The
            # total-CL definitions below are the common comparison metric and
            # match the E/Ew columns written to the native .polar file.
            "E_near_field_solver_induced_CL": final["E_near_field"],
            "Ew_far_field_solver_induced_CL": final["Ew_far_field"],
            "e_near_field_total_CL": final["CL"] ** 2
            / (math.pi * aspect_ratio * final["CDi_near_field"]),
            "e_far_field_total_CL": final["CL"] ** 2
            / (math.pi * aspect_ratio * final["CDiw_far_field"]),
            "reference_aspect_ratio": aspect_ratio,
            "Cm": final["Cm"],
            **metrics,
            "root_bending_limit_Nm": root_limit,
            "root_bending_utilization": metrics[
                "half_wing_root_bending_moment_Nm"
            ]
            / root_limit,
            "root_bending_feasible": metrics[
                "half_wing_root_bending_moment_Nm"
            ]
            <= root_limit * (1.0 + analysis["constraint_relative_tolerance"]),
            "vspaero_execution_count": execution_count,
            "evaluation_seconds": time.perf_counter() - started,
        }
        write_result_csv(state_dir / "aerodynamic_summary.csv", [row])
        summary.append(row)
    write_result_csv(case_dir / "state_summary.csv", summary)
    complete.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "states": len(summary),
                "audit_schema_version": AUDIT_SCHEMA_VERSION,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_case(python: Path, script: Path, project: Path, case_dir: Path, force: bool):
    command = [
        str(python),
        str(script),
        "--worker",
        "--project",
        str(project),
        "--case-dir",
        str(case_dir),
    ]
    if force:
        command.append("--force")
    log = case_dir / "audit.log"
    with log.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            command,
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return case_dir.name, result.returncode == 0, "" if result.returncode == 0 else str(log)


def consolidate(project: Path, case_dirs: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for case_dir in case_dirs:
        summary = case_dir / "state_summary.csv"
        if summary.exists():
            with summary.open(encoding="utf-8-sig") as handle:
                rows.extend(csv.DictReader(handle))
    write_csv(project / "outputs" / "far_field_audit" / "all_results.csv", rows)
    return rows


def main() -> None:
    args = parse_args()
    if args.worker:
        if args.case_dir is None:
            raise ValueError("--case-dir is required in worker mode")
        evaluate_worker(args)
        return
    project = args.project.resolve()
    records = selected_records(source_records(project), args)
    if args.case_id and len(records) != len(set(args.case_id)):
        found = {record["case_id"] for record in records}
        raise ValueError(f"Unknown requested cases: {sorted(set(args.case_id) - found)}")
    case_dirs = prepare_cases(project, records)
    print(f"Prepared {len(case_dirs)} independent far-field audit cases")
    if args.prepare_only:
        return
    if args.consolidate_only:
        print(f"Consolidated {len(consolidate(project, case_dirs))} state results")
        return
    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    workers = args.workers or int(config["runtime"]["workers"])
    python = Path(config["runtime"]["openvsp_python"])
    script = Path(__file__).resolve()
    failures: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_case, python, script, project, case_dir, args.force): case_dir
            for case_dir in case_dirs
        }
        for index, future in enumerate(as_completed(futures), start=1):
            case_id, success, log = future.result()
            print(f"[{index:03d}/{len(case_dirs):03d}] {case_id}: {'ok' if success else 'FAILED'}")
            if not success:
                failures.append({"case_id": case_id, "log": log})
    if failures and workers > 1:
        failed = {row["case_id"] for row in failures}
        failures = []
        print(f"Serial retry for {len(failed)} parallel failures")
        for case_dir in (path for path in case_dirs if path.name in failed):
            case_id, success, log = run_case(python, script, project, case_dir, True)
            print(f"[retry] {case_id}: {'ok' if success else 'FAILED'}")
            if not success:
                failures.append({"case_id": case_id, "log": log})
    rows = consolidate(project, case_dirs)
    failure_path = project / "outputs" / "far_field_audit" / "failures.json"
    failure_path.write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    print(f"Finished with {len(rows)} state results and {len(failures)} failures")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

