"""Re-evaluate the saved four-concept geometry database at Mach 0.1."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--consolidate-only", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case-manifest-index", type=int)
    return parser.parse_args()


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_state(config: dict, cruise_project: Path) -> tuple[dict, dict]:
    sys.path.insert(0, str(cruise_project / "src"))
    from argus_cruise_comparison.atmosphere import isa_state

    atmosphere = isa_state(float(config["altitude_m"]))
    mach = float(config["mach"])
    velocity = mach * atmosphere.speed_of_sound_m_s
    q = 0.5 * atmosphere.density_kg_m3 * velocity**2
    area = float(config["aircraft_scale"]["target_reference_area_m2"])
    target_cl = float(config["target_CL"])
    target_lift = q * area * target_cl
    state = {
        "name": "mach_0p1_fixed_cl",
        **atmosphere.to_dict(),
        "mach": mach,
        "velocity_m_s": velocity,
        "dynamic_pressure_Pa": q,
        "target_CL": target_cl,
        "target_lift_N": target_lift,
        "mass_equivalent_kg": target_lift / 9.80665,
        "reference_area_m2": area,
        "interpretation": config["definition"],
    }
    cruise_scale = load_json(
        cruise_project / "outputs" / "study_definition" / "scale_definition.json"
    )
    return state, cruise_scale


def design_record(path: Path, concept: str, source_group: str) -> dict:
    design_path = next(path.glob("*_design.json"), None)
    design = load_json(design_path) if design_path else {}
    model = path / f"{path.name}.vsp3"
    if not model.exists():
        raise FileNotFoundError(model)
    return {
        "case_id": path.name,
        "concept": concept,
        "source_group": source_group,
        "model_path": str(model),
        "design_path": str(design_path) if design_path else "",
        "control_values": design.get(
            "control_values",
            design.get("segment_deflections_deg", []),
        ),
        "command_units": design.get(
            "command_units",
            "deg" if concept == "conventional_hinged" else "",
        ),
    }


def discover_manifest(config: dict) -> list[dict]:
    cruise = Path(config["source_projects"]["cruise"])
    conventional = Path(config["source_projects"]["conventional"])
    rigid_model = cruise / "outputs" / "rigid_baseline" / "model" / "rigid_baseline.vsp3"
    records = [{
        "case_id": "rigid_baseline",
        "concept": "rigid",
        "source_group": "rigid",
        "model_path": str(rigid_model),
        "design_path": "",
        "control_values": [],
        "command_units": "",
    }]

    for root, group in [
        (cruise / "outputs" / "seed_cases", "seed"),
        (cruise / "outputs" / "optimization_cases", "optimization"),
    ]:
        for design_path in sorted(root.rglob("*_design.json")):
            design = load_json(design_path)
            records.append(
                design_record(design_path.parent, design["concept"], group)
            )

    for design_path in sorted(
        (conventional / "outputs" / "cases").rglob("*_design.json")
    ):
        records.append(
            design_record(
                design_path.parent,
                "conventional_hinged",
                "optimization",
            )
        )

    refinement_root = Path(config["refinement_geometry_root"])
    if refinement_root.exists():
        for design_path in sorted(refinement_root.rglob("*_design.json")):
            design = load_json(design_path)
            records.append(
                design_record(
                    design_path.parent,
                    design["concept"],
                    "mach01_local_refinement",
                )
            )

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for record in records:
        key = (record["concept"], record["case_id"])
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


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


def trim_to_cl_independent_points(
    vsp,
    wing_id: str,
    target_cl: float,
    mach: float,
    native_reference: dict,
    analysis: dict,
    *,
    tolerance: float,
    initial_alpha: float | None = None,
    reference_slope: float | None = None,
) -> tuple[dict, list[dict], list[dict], int]:
    """Trim using independent solves so result-history ordering is irrelevant."""
    from argus_cruise_comparison.vspaero import evaluate, interpolate_alpha

    trace: list[dict] = []
    if initial_alpha is None or reference_slope is None:
        bracket = (0.0, 4.0)
    else:
        bracket = (initial_alpha,)
    for alpha in bracket:
        result, _ = evaluate(
            vsp,
            wing_id,
            alpha,
            mach,
            native_reference,
            analysis,
            loads=False,
        )
        trace.append(result)
    if len(trace) == 2:
        alpha, slope = interpolate_alpha(trace, target_cl)
    else:
        slope = reference_slope
        alpha = trace[0]["alpha_deg"] + (target_cl - trace[0]["CL"]) / slope
    executions = len(trace)
    for _ in range(4):
        final, raw = evaluate(
            vsp,
            wing_id,
            alpha,
            mach,
            native_reference,
            analysis,
            loads=True,
        )
        executions += 1
        trace.append(final)
        if abs(final["CL"] - target_cl) <= tolerance:
            return final, raw, trace, executions
        previous = trace[-2]
        delta_alpha = final["alpha_deg"] - previous["alpha_deg"]
        if abs(delta_alpha) > 1.0e-8:
            secant_slope = (final["CL"] - previous["CL"]) / delta_alpha
            if secant_slope > 1.0e-6:
                slope = secant_slope
        alpha += (target_cl - final["CL"]) / slope
    raise RuntimeError(
        f"Independent-point trim missed tolerance: target={target_cl:.8f}, "
        f"last={final['CL']:.8f}"
    )


def evaluate_one(project: Path, index: int, force: bool) -> None:
    config = load_json(project / "config" / "study_config.json")
    manifest = load_json(project / "outputs" / "study_definition" / "case_manifest.json")
    record = manifest[index]
    case_dir = project / "outputs" / "cases" / record["concept"] / record["case_id"]
    summary_path = case_dir / "summary.csv"
    if summary_path.exists() and not force:
        return
    case_dir.mkdir(parents=True, exist_ok=True)
    working_model = case_dir / f"{record['case_id']}.vsp3"
    shutil.copy2(record["model_path"], working_model)

    cruise_project = Path(config["source_projects"]["cruise"])
    sys.path.insert(0, str(cruise_project / "src"))
    from argus_cruise_comparison.vspaero import (
        collapse_spanwise_loads,
        configure_geometry,
        integrate_load_metrics,
    )

    state = load_json(project / "outputs" / "study_definition" / "flight_state.json")
    scale = load_json(project / "outputs" / "study_definition" / "scale_definition.json")
    analysis = config["aerodynamic_analysis"]
    region = config["concept_regions"][record["concept"]]

    started = time.perf_counter()
    vsp = load_vsp(Path(config["runtime"]["openvsp_root"]))
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(working_model))
    vsp.Update()
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    if not wing_id:
        raise RuntimeError(f"Wing geometry not found: {config['wing_name']}")
    configure_geometry(vsp, analysis)
    initial_alpha = None
    reference_slope = None
    rigid_summary = (
        project / "outputs" / "cases" / "rigid" / "rigid_baseline"
        / "summary.csv"
    )
    rigid_trace = rigid_summary.parent / "trim_trace.csv"
    if record["concept"] != "rigid" and rigid_summary.exists() and rigid_trace.exists():
        with rigid_summary.open(encoding="utf-8-sig") as handle:
            initial_alpha = float(next(csv.DictReader(handle))["alpha_trim_deg"])
        with rigid_trace.open(encoding="utf-8-sig") as handle:
            bracket_rows = list(csv.DictReader(handle))[:2]
        reference_slope = (
            float(bracket_rows[1]["CL"]) - float(bracket_rows[0]["CL"])
        ) / (
            float(bracket_rows[1]["alpha_deg"])
            - float(bracket_rows[0]["alpha_deg"])
        )

    final, raw, trace, executions = trim_to_cl_independent_points(
        vsp,
        wing_id,
        state["target_CL"],
        state["mach"],
        config["native_geometry"],
        analysis,
        tolerance=analysis["strict_cl_tolerance"],
        initial_alpha=initial_alpha,
        reference_slope=reference_slope,
    )
    strips = collapse_spanwise_loads(
        raw,
        state,
        scale,
        config["native_geometry"],
        morph_eta_start=float(region[0]),
        morph_eta_end=float(region[1]),
    )
    metrics = integrate_load_metrics(strips)
    # The inherited moment proxy is not a local actuator hinge moment and was
    # withdrawn in the July 2026 audit. Do not propagate it into this study.
    metrics.pop("morph_region_moment_proxy_Nm", None)
    for strip in strips:
        strip.pop("moment_proxy_Nm_per_m", None)
    row = {
        **{key: record[key] for key in ["case_id", "concept", "source_group"]},
        "model_path": record["model_path"],
        "working_model_path": str(working_model),
        "mach": state["mach"],
        "altitude_m": state["altitude_m"],
        "target_CL": state["target_CL"],
        "CL": final["CL"],
        "CL_error": final["CL"] - state["target_CL"],
        "alpha_trim_deg": final["alpha_deg"],
        "CD": final["CD"],
        "CDi": final["CDi"],
        "Cm": final["Cm"],
        **metrics,
        "vspaero_execution_count": executions,
        "evaluation_seconds": time.perf_counter() - started,
        "control_values_json": json.dumps(record["control_values"]),
        "command_units": record["command_units"],
    }
    write_csv(case_dir / "trim_trace.csv", trace)
    write_csv(case_dir / "spanwise_loads.csv", strips)
    write_csv(case_dir / "raw_vspaero_loads.csv", raw)
    write_csv(summary_path, [row])


def run_subprocess(project: Path, index: int, force: bool, python: Path) -> tuple[int, bool, str]:
    command = [
        str(python),
        str(Path(__file__).resolve()),
        "--project",
        str(project),
        "--worker",
        "--case-manifest-index",
        str(index),
    ]
    if force:
        command.append("--force")
    log = project / "outputs" / "logs" / f"case_{index:03d}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            command,
            cwd=project,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return index, result.returncode == 0, str(log)


def consolidate(project: Path, manifest: list[dict]) -> None:
    rows: list[dict] = []
    for record in manifest:
        path = (
            project / "outputs" / "cases" / record["concept"]
            / record["case_id"] / "summary.csv"
        )
        if path.exists():
            with path.open(encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    rows.append({
                        key: value
                        for key, value in row.items()
                        if "moment_proxy" not in key
                    })
    write_csv(project / "outputs" / "evaluations" / "all_results.csv", rows)


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    config = load_json(project / "config" / "study_config.json")
    if args.worker:
        evaluate_one(project, args.case_manifest_index, args.force)
        return

    cruise = Path(config["source_projects"]["cruise"])
    state, scale = build_state(config, cruise)
    definition = project / "outputs" / "study_definition"
    definition.mkdir(parents=True, exist_ok=True)
    manifest = discover_manifest(config)
    (definition / "flight_state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )
    (definition / "scale_definition.json").write_text(
        json.dumps(scale, indent=2) + "\n", encoding="utf-8"
    )
    (definition / "case_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(definition / "case_manifest.csv", manifest)
    print(
        f"Mach={state['mach']}, CL={state['target_CL']:.9f}, "
        f"q={state['dynamic_pressure_Pa']:.3f} Pa, cases={len(manifest)}"
    )
    if args.manifest_only:
        return
    if args.consolidate_only:
        consolidate(project, manifest)
        return

    workers = args.workers or int(config["runtime"]["workers"])
    python = Path(config["runtime"]["openvsp_python"])
    failures: list[tuple[int, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_subprocess, project, index, args.force, python): index
            for index in range(len(manifest))
        }
        completed = 0
        for future in as_completed(futures):
            index, ok, log = future.result()
            completed += 1
            label = f"{manifest[index]['concept']}/{manifest[index]['case_id']}"
            print(f"[{completed}/{len(manifest)}] {'OK' if ok else 'FAIL'} {label}")
            if not ok:
                failures.append((index, log))
    consolidate(project, manifest)
    if failures:
        details = ", ".join(f"{index}: {log}" for index, log in failures)
        raise SystemExit(f"{len(failures)} evaluations failed: {details}")


if __name__ == "__main__":
    main()

