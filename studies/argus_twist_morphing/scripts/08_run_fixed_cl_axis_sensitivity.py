from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path


TARGET_CL = 0.428277635108


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument(
        "--openvsp-root",
        type=Path,
        default=Path(r"<OPENVSP_ROOT>"),
    )
    parser.add_argument("--cl-tolerance", type=float, default=2.0e-5)
    parser.add_argument("--max-iterations", type=int, default=6)
    return parser.parse_args()


def load_doe_module(project):
    path = project / "scripts" / "05_run_fixed_cl_twist_doe.py"
    spec = importlib.util.spec_from_file_location("fixed_cl_twist_doe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def add_axis_moment(loads, axis, reference_axis, config):
    q = 0.5 * config["rho_kg_m3"] * config["velocity_m_s"] ** 2
    total = 0.0
    absolute_total = 0.0
    for row in loads:
        chord = row["chord_m"]
        cmy_reference = row["section_pitch_moment_N"] / (q * chord**2)
        cmy_axis = cmy_reference + row["sectional_cl"] * (
            reference_axis - axis
        )
        moment_per_span = q * chord**2 * cmy_axis
        row["axis_x_over_c"] = axis
        row["section_pitch_moment_about_axis_N"] = moment_per_span
        total += moment_per_span * row["dy_m"]
        absolute_total += abs(moment_per_span) * row["dy_m"]
    return {
        "morph_region_axis_moment_proxy_Nm": sum(
            row["section_pitch_moment_about_axis_N"] * row["dy_m"]
            for row in loads
            if row["in_morph_region"]
        ),
        "morph_region_abs_axis_moment_proxy_Nm": sum(
            abs(row["section_pitch_moment_about_axis_N"]) * row["dy_m"]
            for row in loads
            if row["in_morph_region"]
        ),
        "half_wing_axis_moment_proxy_Nm": total,
        "half_wing_abs_axis_moment_proxy_Nm": absolute_total,
    }


def main():
    args = parse_args()
    doe = load_doe_module(args.project)
    config = json.loads(
        (args.project / "config" / "baseline_config.json").read_text(encoding="utf-8")
    )
    study = json.loads(
        (args.project / "config" / "twist_study_config.json").read_text(encoding="utf-8")
    )
    sensitivity = json.loads(
        (args.project / "config" / "axis_sensitivity_config.json").read_text(
            encoding="utf-8"
        )
    )
    case_root = args.project / "outputs" / "axis_sensitivity_cases"
    output = args.project / "outputs" / "fixed_cl_axis_sensitivity"
    output.mkdir(parents=True, exist_ok=True)
    manifest = read_csv(case_root / "axis_sensitivity_manifest.csv")
    vsp = doe.load_vsp(args.openvsp_root)
    summary = []

    for design in manifest:
        case_id = design["case_id"]
        axis = float(design["axis_x_over_c"])
        model = Path(design["model"])
        print(f"Fixed-CL axis evaluation: {case_id}")
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(model))
        wing_id = vsp.FindGeom(config["wing_name"], 0)
        doe.configure_geometry(vsp, config)
        final, raw, trace = doe.trim(
            vsp, wing_id, config, args.cl_tolerance, args.max_iterations
        )
        loads = doe.collapse_loads(
            raw, case_id, config, study["eta_start"], study["eta_end"]
        )
        moment_metrics = add_axis_moment(
            loads,
            axis,
            sensitivity["moment_reference_x_over_c"],
            config,
        )
        row = {
            "case_id": case_id,
            "case_name": design["case_name"],
            "axis_x_over_c": axis,
            "twist_max_deg": float(design["twist_max_deg"]),
            "max_le_travel_mm": float(design["max_le_travel_mm"]),
            "max_te_travel_mm": float(design["max_te_travel_mm"]),
            "alpha_trim_deg": final["alpha_deg"],
            "CL_target": TARGET_CL,
            "CL": final["CL"],
            "CD": final["CD"],
            "CDi": final["CDi"],
            "Cm": final["Cm"],
            **doe.metrics(loads),
            **moment_metrics,
        }
        summary.append(row)
        write_csv(output / f"{case_id}_trim_trace.csv", trace)
        write_csv(output / f"{case_id}_spanwise_loads.csv", loads)
        write_csv(output / f"{case_id}_fixed_cl_summary.csv", [row])

    baselines = {
        row["axis_x_over_c"]: row
        for row in summary
        if row["case_name"] == "baseline"
    }
    original_baseline = baselines[0.25]
    for row in summary:
        baseline = baselines[row["axis_x_over_c"]]
        row["CDi_reduction_vs_axis_baseline_percent"] = 100.0 * (
            baseline["CDi"] - row["CDi"]
        ) / baseline["CDi"]
        row["root_bending_change_vs_axis_baseline_percent"] = 100.0 * (
            row["half_wing_root_bending_moment_Nm"]
            - baseline["half_wing_root_bending_moment_Nm"]
        ) / baseline["half_wing_root_bending_moment_Nm"]
        row["outer_lift_change_vs_axis_baseline_percent"] = 100.0 * (
            row["morph_region_lift_N"] - baseline["morph_region_lift_N"]
        ) / baseline["morph_region_lift_N"]
        row["axis_moment_change_vs_axis_baseline_percent"] = 100.0 * (
            row["morph_region_abs_axis_moment_proxy_Nm"]
            - baseline["morph_region_abs_axis_moment_proxy_Nm"]
        ) / baseline["morph_region_abs_axis_moment_proxy_Nm"]
        row["baseline_CDi_change_vs_x25_percent"] = 100.0 * (
            baseline["CDi"] - original_baseline["CDi"]
        ) / original_baseline["CDi"]

    write_csv(output / "fixed_cl_axis_sensitivity_summary.csv", summary)
    print(f"Wrote {len(summary)} fixed-CL axis cases to {output}")


if __name__ == "__main__":
    main()


