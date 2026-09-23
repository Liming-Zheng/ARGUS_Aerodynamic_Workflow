"""Run strict early- and late-cruise VSPAERO trims for the rigid baseline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--alpha-low", type=float, default=0.0)
    parser.add_argument("--alpha-high", type=float, default=4.0)
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


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
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
    flight_states = json.loads(
        (
            project
            / "outputs"
            / "study_definition"
            / "flight_states.json"
        ).read_text(encoding="utf-8")
    )
    scale_definition = json.loads(
        (
            project
            / "outputs"
            / "study_definition"
            / "scale_definition.json"
        ).read_text(encoding="utf-8")
    )
    output_dir = project / "outputs" / "rigid_baseline"
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir = output_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    source_model = Path(config["source_model"])
    working_model = model_dir / "rigid_baseline.vsp3"
    shutil.copy2(source_model, working_model)
    summary_path = output_dir / "rigid_baseline_summary.csv"
    if summary_path.exists() and not args.force:
        print(f"Existing result retained: {summary_path}")
        return

    vsp = load_vsp(Path(config["runtime"]["openvsp_root"]))
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(working_model))
    vsp.Update()
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    if not wing_id:
        raise RuntimeError(f"Wing geometry not found: {config['wing_name']}")
    configure_geometry(vsp, config["aerodynamic_analysis"])

    morph = config["morphing"]
    native_reference = config["native_geometry"]
    tolerance = config["aerodynamic_analysis"]["strict_cl_tolerance"]
    summary: list[dict] = []
    root_bending_limit = None

    for state in flight_states:
        started = time.perf_counter()
        final, raw_loads, trace, execution_count = trim_to_cl(
            vsp,
            wing_id,
            state["target_CL"],
            state["mach"],
            native_reference,
            config["aerodynamic_analysis"],
            alpha_low=args.alpha_low,
            alpha_high=args.alpha_high,
            tolerance=tolerance,
        )
        strips = collapse_spanwise_loads(
            raw_loads,
            state,
            scale_definition,
            native_reference,
            morph_eta_start=morph["eta_start"],
            morph_eta_end=morph["eta_end"],
        )
        metrics = integrate_load_metrics(strips)
        if state["name"] == "early_cruise":
            root_bending_limit = metrics["half_wing_root_bending_moment_Nm"]
        constraint_result = constraint_status(
            root_bending_moment_Nm=metrics[
                "half_wing_root_bending_moment_Nm"
            ],
            root_bending_limit_Nm=(
                root_bending_limit
                if root_bending_limit is not None
                else float("inf")
            ),
            max_abs_command=0.0,
            max_abs_command_limit=1.0,
            max_adjacent_delta=0.0,
            max_adjacent_delta_limit=1.0,
            relative_tolerance=config["aerodynamic_analysis"][
                "constraint_relative_tolerance"
            ],
        )
        state_dir = output_dir / state["name"]
        state_dir.mkdir(parents=True, exist_ok=True)
        write_csv(state_dir / "trim_trace.csv", trace)
        write_csv(state_dir / "spanwise_loads.csv", strips)
        write_csv(state_dir / "raw_vspaero_loads.csv", raw_loads)
        row = {
            "case_id": f"rigid_baseline_{state['name']}",
            "flight_state": state["name"],
            "altitude_m": state["altitude_m"],
            "mach": state["mach"],
            "density_kg_m3": state["density_kg_m3"],
            "velocity_m_s": state["velocity_m_s"],
            "dynamic_pressure_Pa": state["dynamic_pressure_Pa"],
            "target_lift_N": state["target_lift_N"],
            "target_CL": state["target_CL"],
            "alpha_trim_deg": final["alpha_deg"],
            "CL": final["CL"],
            "CL_error": final["CL"] - state["target_CL"],
            "CD": final["CD"],
            "CDi": final["CDi"],
            "Cm": final["Cm"],
            **metrics,
            "root_bending_limit_Nm": root_bending_limit,
            "root_bending_constraint_active": (
                "absolute_root_bending"
                in constraint_result["active_constraints"]
            ),
            "vspaero_execution_count": execution_count,
            "evaluation_seconds": time.perf_counter() - started,
        }
        summary.append(row)
        print(
            f"{state['name']}: CL={row['CL']:.6f}, "
            f"CDi={row['CDi']:.8f}, "
            f"Mroot={row['half_wing_root_bending_moment_Nm'] / 1e6:.3f} MN m"
        )

    write_csv(summary_path, summary)
    definition = {
        "root_bending_limit_strategy": (
            "rigid early-cruise half-wing root bending moment"
        ),
        "root_bending_limit_Nm": root_bending_limit,
        "hinge_moment_constraint_enabled": False,
        "source_model": config["source_model"],
        "working_model": str(working_model),
        "note": (
            "Absolute loads are aircraft-scale SI values. VSPAERO is run on "
            "the geometrically similar NASA model with native reference values."
        ),
    }
    (output_dir / "constraint_definition.json").write_text(
        json.dumps(definition, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()

