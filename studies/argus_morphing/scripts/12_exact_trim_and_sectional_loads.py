from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--cl-tolerance", type=float, default=2.0e-5)
    parser.add_argument("--max-iterations", type=int, default=6)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for rel in ["python/openvsp", "python/openvsp_config", "python/degen_geom", "python/utilities"]:
        sys.path.insert(0, str(root / rel))
    import openvsp as vsp

    return vsp


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None):
    if not rows:
        return
    fields = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


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


def configure_geometry(vsp, config):
    analysis = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_NONE)
    set_int(vsp, analysis, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(analysis)


def evaluate(vsp, wing_id, alpha, mach, config, include_loads=False):
    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(vsp, analysis, "Sref", config["reference_area_m2"])
    set_double(vsp, analysis, "cref", config["reference_chord_m"])
    set_double(vsp, analysis, "bref", config["reference_span_m"])
    set_string(vsp, analysis, "WingID", wing_id)
    for prefix, value in [("Alpha", alpha), ("Beta", 0.0), ("Mach", mach)]:
        set_double(vsp, analysis, f"{prefix}Start", value)
        set_double(vsp, analysis, f"{prefix}End", value)
        set_int(vsp, analysis, f"{prefix}Npts", 1)
    set_int(vsp, analysis, "WakeNumIter", config["wake_iterations"])
    vsp.ExecAnalysis(analysis)

    history_id = vsp.FindLatestResultsID("VSPAERO_History")
    result = {
        "alpha_deg": alpha,
        "CL": last(vsp, history_id, ["CLtot", "CL"]),
        "CD": last(vsp, history_id, ["CDtot", "CD"]),
        "CDi": last(vsp, history_id, ["CDi"]),
        "Cm": last(vsp, history_id, ["CMytot", "CMy", "Cm"]),
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


def exact_trim(vsp, wing_id, alpha_guess, cl_target, mach, config, tolerance, iterations):
    a0 = alpha_guess - 0.25
    a1 = alpha_guess + 0.25
    p0, _ = evaluate(vsp, wing_id, a0, mach, config)
    p1, _ = evaluate(vsp, wing_id, a1, mach, config)
    trace = [p0, p1]
    for _ in range(iterations):
        denominator = p1["CL"] - p0["CL"]
        if abs(denominator) < 1.0e-10:
            raise RuntimeError("Near-zero lift slope during exact trim")
        alpha = a1 + (cl_target - p1["CL"]) * (a1 - a0) / denominator
        point, _ = evaluate(vsp, wing_id, alpha, mach, config)
        trace.append(point)
        if abs(point["CL"] - cl_target) <= tolerance:
            final, loads = evaluate(vsp, wing_id, alpha, mach, config, include_loads=True)
            trace.append(final)
            return final, loads, trace
        a0, p0 = a1, p1
        a1, p1 = alpha, point
    raise RuntimeError(
        f"Trim did not converge: target={cl_target:.9f}, last={p1['CL']:.9f}"
    )


def collapse_half_wing(raw_rows, case_id, config, design):
    q = 0.5 * config["rho_kg_m3"] * config["velocity_m_s"] ** 2
    semi_span = 0.5 * config["reference_span_m"]
    bins = defaultdict(list)
    for row in raw_rows:
        bins[round(abs(float(row.get("Yavg", 0.0))), 8)].append(row)

    output = []
    for y_key in sorted(bins):
        items = bins[y_key]

        def average(name):
            values = [float(item.get(name, 0.0)) for item in items]
            return sum(values) / len(values)

        y = float(y_key)
        chord = average("Chord")
        cl = average("cl")
        cd = average("cd")
        cmy = average("cmy")
        eta = y / semi_span
        output.append({
            "case_id": case_id,
            "eta": eta,
            "y_m": y,
            "dy_m": average("dSpan"),
            "chord_m": chord,
            "sectional_cl": cl,
            "sectional_cd": cd,
            "lift_per_span_N_per_m": q * chord * cl,
            "drag_per_span_N_per_m": q * chord * cd,
            "force_x_N_per_m": q * chord * average("cx"),
            "force_y_N_per_m": q * chord * average("cy"),
            "force_z_up_N_per_m": -q * chord * average("cz"),
            "section_pitch_moment_N": q * chord**2 * cmy,
            "hinge_moment_proxy_N": q
            * chord**2
            * (cmy + (float(design["x_h_over_c"]) - 0.25) * cl),
            "in_morph_region": float(design["eta_start"]) <= eta <= float(design["eta_end"]),
        })
    return output


def load_metrics(rows, design):
    morph_rows = [row for row in rows if row["in_morph_region"]]
    total_lift_half = sum(row["lift_per_span_N_per_m"] * row["dy_m"] for row in rows)
    root_bending = sum(
        row["lift_per_span_N_per_m"] * row["dy_m"] * row["y_m"] for row in rows
    )
    outer_lift = sum(
        row["lift_per_span_N_per_m"] * row["dy_m"] for row in morph_rows
    )
    hinge_torque_proxy = sum(
        row["hinge_moment_proxy_N"] * row["dy_m"] for row in morph_rows
    )
    semi_span = max(row["y_m"] / row["eta"] for row in rows if row["eta"] > 0)
    eta_start_y = float(design["eta_start"]) * semi_span
    morph_root_bending = sum(
        row["lift_per_span_N_per_m"]
        * row["dy_m"]
        * max(0.0, row["y_m"] - eta_start_y)
        for row in morph_rows
    )
    return {
        "half_wing_lift_N": total_lift_half,
        "half_wing_root_bending_moment_Nm": root_bending,
        "morph_region_lift_N": outer_lift,
        "morph_region_lift_fraction": outer_lift / total_lift_half,
        "morph_region_bending_about_eta_start_Nm": morph_root_bending,
        "morph_region_hinge_torque_proxy_Nm": hinge_torque_proxy,
    }


def save_figure(fig, path):
    fig.savefig(path.with_suffix(".png"), dpi=200, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def make_plots(output, all_loads, summary):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for case_id, rows in all_loads.items():
        label = "Refined baseline" if case_id == "refined_baseline" else case_id.replace("doe_", "")
        ax.plot(
            [row["eta"] for row in rows],
            [row["lift_per_span_N_per_m"] for row in rows],
            lw=2 if case_id == "refined_baseline" else 1.5,
            ls="--" if case_id == "refined_baseline" else "-",
            label=label,
        )
    ax.axvspan(0.6, 0.95, color="#dce8df", alpha=0.45, label="Morphing region")
    ax.set_xlabel("eta = y/(b/2)")
    ax.set_ylabel("Lift per span [N/m]")
    ax.set_title("Exact fixed-CL spanwise lift distributions")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    save_figure(fig, output / "exact_trim_spanwise_lift")

    candidates = [row for row in summary if row["case_id"] != "refined_baseline"]
    names = [f"#{index + 1}" for index in range(len(candidates))]
    values = [float(row["morph_region_hinge_torque_proxy_Nm"]) for row in candidates]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(names, values, color="#237a72")
    ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=8)
    ax.set_xlabel("DOE candidate rank")
    ax.set_ylabel("Integrated hinge-moment proxy [N m]")
    ax.set_title("Morphing-region aerodynamic torque proxy")
    ax.grid(axis="y", alpha=0.25)
    save_figure(fig, output / "candidate_hinge_moment_proxy")

    fig, ax = plt.subplots(figsize=(8, 5.2))
    for index, row in enumerate(candidates, start=1):
        x = float(row["root_bending_change_percent_vs_baseline"])
        y = -float(row["CDi_change_percent_vs_baseline"])
        ax.scatter(x, y, s=75, color="#237a72")
        ax.annotate(
            f"#{index}",
            (x, y),
            xytext=(6, 5),
            textcoords="offset points",
            fontsize=9,
        )
    ax.set_xlabel("Half-wing root bending increase [%]")
    ax.set_ylabel("Induced-drag reduction [%]")
    ax.set_title("Aerodynamic benefit versus structural load penalty")
    ax.grid(alpha=0.25)
    save_figure(fig, output / "drag_benefit_vs_root_bending")


def load_cached(path, load_path):
    summary = read_csv(path)[0]
    numeric_exceptions = {"case_id", "shape_type", "trim_converged", "notes"}
    summary = {
        key: value if key in numeric_exceptions else float(value)
        for key, value in summary.items()
    }
    loads = []
    for item in read_csv(load_path):
        loads.append({
            key: (
                value
                if key == "case_id"
                else value == "True"
                if key == "in_morph_region"
                else float(value)
            )
            for key, value in item.items()
        })
    return summary, loads


def main():
    args = parse_args()
    project = args.project.resolve()
    output = project / "outputs" / "exact_trim_loads"
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads(
        (project / "config" / "baseline_config.json").read_text(encoding="utf-8")
    )
    baseline_coeff = read_csv(
        project / "outputs" / "refined_baseline" / "refined_baseline_vspaero_coefficients.csv"
    )[0]
    cl_target = float(baseline_coeff["CL"])
    ranked = read_csv(project / "outputs" / "doe" / "minimal_doe_ranked.csv")[: args.top]
    cases = [{
        "case_id": "refined_baseline",
        "model": project / "outputs" / "refined_baseline" / "baseline_wing_only_refined.vsp3",
        "mach": config["mach"],
        "alpha_guess": config["default_alpha_deg"],
        "x_h_over_c": 0.5,
        "eta_start": config["primary_outer_eta"],
        "eta_end": 0.95,
        "A_max_over_c": 0.0,
        "shape_type": "baseline",
        "rank": 0,
    }]
    for rank, row in enumerate(ranked, start=1):
        case_id = row["case_id"]
        case_dir = project / "outputs" / "doe" / case_id
        design = json.loads(
            (case_dir / f"{case_id}_design.json").read_text(encoding="utf-8")
        )
        cases.append({
            **design,
            "model": case_dir / f"{case_id}.vsp3",
            "alpha_guess": float(row["alpha_trim_deg"]),
            "rank": rank,
        })

    vsp = load_vsp(args.openvsp_root)
    summary = []
    all_loads = {}
    for design in cases:
        case_id = design["case_id"]
        summary_path = output / f"{case_id}_exact_trim.csv"
        load_path = output / f"{case_id}_spanwise_load.csv"
        if summary_path.exists() and load_path.exists() and not args.force:
            row, loads = load_cached(summary_path, load_path)
            summary.append(row)
            all_loads[case_id] = loads
            print(f"resume: {case_id}")
            continue

        print(f"running exact trim: {case_id}")
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(design["model"]))
        vsp.Update()
        wing_id = vsp.FindGeom(config["wing_name"], 0)
        configure_geometry(vsp, config)
        final, raw_loads, trace = exact_trim(
            vsp,
            wing_id,
            float(design["alpha_guess"]),
            cl_target,
            float(design["mach"]),
            config,
            args.cl_tolerance,
            args.max_iterations,
        )
        half_loads = collapse_half_wing(raw_loads, case_id, config, design)
        metrics = load_metrics(half_loads, design)
        row = {
            "case_id": case_id,
            "rank": design["rank"],
            "shape_type": design["shape_type"],
            "x_h_over_c": design["x_h_over_c"],
            "A_max_over_c": design["A_max_over_c"],
            "eta_start": design["eta_start"],
            "eta_end": design["eta_end"],
            "alpha_trim_deg": final["alpha_deg"],
            "CL_target": cl_target,
            "CL": final["CL"],
            "CL_error": final["CL"] - cl_target,
            "CD": final["CD"],
            "CDi": final["CDi"],
            "Cm": final["Cm"],
            **metrics,
            "trim_converged": abs(final["CL"] - cl_target) <= args.cl_tolerance,
            "notes": "Hinge torque is a VLM sectional-moment proxy about x_h/c, not a structural actuator sizing result.",
        }
        summary.append(row)
        all_loads[case_id] = half_loads
        write_csv(summary_path, [row])
        write_csv(output / f"{case_id}_trim_trace.csv", trace)
        write_csv(load_path, half_loads)
        raw_fields = ["case_id", "station_index"] + sorted(
            set().union(*(item.keys() for item in raw_loads)) - {"case_id", "station_index"}
        )
        write_csv(
            output / f"{case_id}_vspaero_load_raw.csv",
            [{"case_id": case_id, **item} for item in raw_loads],
            raw_fields,
        )

    baseline = next(row for row in summary if row["case_id"] == "refined_baseline")
    for row in summary:
        row["CDi_change_percent_vs_baseline"] = (
            100.0 * (float(row["CDi"]) - float(baseline["CDi"])) / float(baseline["CDi"])
        )
        row["root_bending_change_percent_vs_baseline"] = (
            100.0
            * (
                float(row["half_wing_root_bending_moment_Nm"])
                - float(baseline["half_wing_root_bending_moment_Nm"])
            )
            / float(baseline["half_wing_root_bending_moment_Nm"])
        )
    write_csv(output / "exact_trim_load_summary.csv", summary)
    make_plots(output, all_loads, summary)

    candidates = [row for row in summary if row["case_id"] != "refined_baseline"]
    best = min(candidates, key=lambda row: float(row["CDi"]))
    report = [
        "ARGUS exact fixed-CL candidate evaluation",
        "",
        f"CL target: {cl_target:.9f}",
        f"Cases: refined baseline + top {len(candidates)} DOE candidates",
        f"CL tolerance: {args.cl_tolerance:.1e}",
        "",
        "Best exact candidate:",
        f"case_id: {best['case_id']}",
        f"alpha_trim_deg: {float(best['alpha_trim_deg']):.6f}",
        f"CL_error: {float(best['CL_error']):+.3e}",
        f"CDi: {float(best['CDi']):.9f}",
        f"CDi change vs baseline: {float(best['CDi_change_percent_vs_baseline']):+.3f} %",
        f"root bending change vs baseline: {float(best['root_bending_change_percent_vs_baseline']):+.3f} %",
        f"morph-region lift: {float(best['morph_region_lift_N']):.3f} N per half-wing",
        f"morph-region bending about eta_start: {float(best['morph_region_bending_about_eta_start_Nm']):.3f} N m",
        f"hinge-moment proxy: {float(best['morph_region_hinge_torque_proxy_Nm']):.3f} N m",
        "",
        "Caution:",
        "The hinge-moment value is derived from VSPAERO sectional moments and a",
        "quarter-chord force-arm approximation. It is suitable for early comparison,",
        "not final actuator sizing. Pressure-resolved CFD or wind-tunnel data and a",
        "structural load path are required for final actuator loads.",
    ]
    (output / "exact_trim_load_summary.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    print("\n".join(report))


if __name__ == "__main__":
    main()


