from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_morphing.load_metrics import (  # noqa: E402
    elliptic_distribution,
    elliptic_error,
    normalized_distribution,
    outer_lift_fraction,
    root_bending_moment,
    strip_outer_lift_fraction,
    strip_root_bending_moment,
    trapezoid,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    return parser.parse_args()


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(row, name, default=0.0):
    try:
        return float(row.get(name, default))
    except (TypeError, ValueError):
        return default


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def save_figure(fig, base_path: Path):
    fig.savefig(base_path.with_suffix(".png"), dpi=200, bbox_inches="tight")
    fig.savefig(base_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def make_load_table(raw_rows: list[dict], config: dict, semi_span: float):
    q = 0.5 * config["load_condition_rho_kg_m3"] * config["load_condition_velocity_m_s"] ** 2
    native_to_m = config["native_length_to_m"]
    grouped = defaultdict(list)
    for row in raw_rows:
        grouped[row["case_id"]].append(row)

    output = []
    metrics = []
    elliptic_plot_data = {}
    for case_id, rows in grouped.items():
        # VSPAERO can emit both sides. Collapse them onto the positive half-wing.
        bins = defaultdict(list)
        for row in rows:
            y = abs(number(row, "Yavg"))
            bins[round(y, 8)].append(row)
        half_rows = []
        for y_key in sorted(bins):
            items = bins[y_key]
            avg = lambda name: sum(number(item, name) for item in items) / len(items)
            y = float(y_key) * native_to_m
            half_rows.append({
                "y": y,
                "chord": avg("Chord") * native_to_m,
                "dspan": avg("dSpan") * native_to_m,
                "sectional_cl": avg("cl"),
                "sectional_cd": avg("cd"),
                "sectional_cdi": avg("cdi"),
                "cx": avg("cx"),
                "cy": avg("cy"),
                "cz": avg("cz"),
                "cmx": avg("cmx"),
                "cmy": avg("cmy"),
                "cmz": avg("cmz"),
            })
        y = [row["y"] for row in half_rows]
        widths = [row["dspan"] for row in half_rows]
        eta = [value / (semi_span * native_to_m) for value in y]
        lift = [q * row["chord"] * row["sectional_cl"] for row in half_rows]
        drag = [q * row["chord"] * row["sectional_cd"] for row in half_rows]
        for index, row in enumerate(half_rows):
            output.append({
                "case_id": case_id,
                "eta": eta[index],
                "y": row["y"],
                "dy": row["dspan"],
                "chord": row["chord"],
                "sectional_cl": row["sectional_cl"],
                "lift_per_span": lift[index],
                "drag_per_span": drag[index],
                "force_x": q * row["chord"] * row["cx"],
                "force_y": q * row["chord"] * row["cy"],
                "force_z": -q * row["chord"] * row["cz"],
                "moment_x": q * row["chord"] ** 2 * row["cmx"],
                "moment_y": q * row["chord"] ** 2 * row["cmy"],
                "moment_z": q * row["chord"] ** 2 * row["cmz"],
                "notes": "SI values converted from native-foot geometry at the native VSPAERO condition; force_z is positive upward.",
            })
        total_lift_half = sum(load * width for load, width in zip(lift, widths))
        reference = elliptic_distribution(y, semi_span, total_lift_half)
        max_index = max(range(len(half_rows)), key=lambda i: half_rows[i]["sectional_cl"])
        metric = {
            "case_id": case_id,
            "root_bending_moment": strip_root_bending_moment(y, widths, lift),
            "elliptic_error": elliptic_error(y, lift, semi_span),
            "outer_wing_lift_fraction": strip_outer_lift_fraction(eta, widths, lift, config["primary_outer_eta"]),
            "max_sectional_cl": half_rows[max_index]["sectional_cl"],
            "eta_of_max_sectional_cl": eta[max_index],
            "notes": f"Half-wing; root moment positive for upward lift; outer fraction eta>={config['primary_outer_eta']}",
        }
        for threshold in config["outer_eta_thresholds"]:
            metric[f"outer_lift_fraction_eta_{threshold:.2f}"] = strip_outer_lift_fraction(eta, widths, lift, threshold)
        metrics.append(metric)
        elliptic_plot_data[case_id] = (eta, normalized_distribution(y, lift), normalized_distribution(y, reference))
    return output, metrics, elliptic_plot_data


def merge_coefficients(metrics: list[dict], coefficient_rows: list[dict]):
    coeff_by_id = {row["case_id"]: row for row in coefficient_rows}
    for row in metrics:
        coeff = coeff_by_id[row["case_id"]]
        for field in ["CL", "CD", "CDi", "Cm"]:
            row[field] = coeff.get(field, "")
    return metrics


def plot_planform(output: Path):
    sections = read_csv(output / "baseline_section_table.csv")
    native_to_m = 0.3048
    y = [number(row, "y") * native_to_m for row in sections]
    xle = [number(row, "x_le") * native_to_m for row in sections]
    chord = [number(row, "chord") * native_to_m for row in sections]
    xte = [a + b for a, b in zip(xle, chord)]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.fill(xle + list(reversed(xte)), y + list(reversed(y)), color="#dce8ef", edgecolor="#174a6b")
    ax.plot(xle, y, color="#174a6b", label="Leading edge")
    ax.plot(xte, y, color="#237a72", label="Trailing edge")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Wing-local x [m]")
    ax.set_ylabel("Semispan y [m]")
    ax.set_title("NASA EET cruise wing: wing-only baseline")
    ax.grid(alpha=0.25)
    ax.legend()
    save_figure(fig, output / "baseline_planform")


def plot_airfoils(output: Path):
    rows = read_csv(output / "raw" / "baseline_airfoil_points.csv")
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["section_id"], row["surface"])].append(row)
    section_ids = sorted({key[0] for key in grouped}, key=int)
    fig, ax = plt.subplots(figsize=(10, 5))
    for section_id in section_ids:
        for surface in ["upper", "lower"]:
            points = sorted(grouped[(section_id, surface)], key=lambda row: int(row["point_index"]))
            ax.plot(
                [number(row, "x_over_c") for row in points],
                [number(row, "z_over_c") for row in points],
                lw=1.0,
                label=f"section {section_id}" if surface == "upper" else None,
            )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x/c")
    ax.set_ylabel("z/c")
    ax.set_title("Baseline OpenVSP airfoil sections")
    ax.grid(alpha=0.25)
    ax.legend(ncol=3, fontsize=8)
    save_figure(fig, output / "baseline_airfoil_sections")


def plot_loads(output: Path, load_rows: list[dict], config: dict, elliptic_data):
    selected = f"baseline_a{config['default_alpha_deg']:+05.1f}".replace("+", "p").replace("-", "m")
    rows = [row for row in load_rows if row["case_id"] == selected]
    rows.sort(key=lambda row: number(row, "eta"))
    eta = [number(row, "eta") for row in rows]
    cl = [number(row, "sectional_cl") for row in rows]
    lift = [number(row, "lift_per_span") for row in rows]

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(eta, cl, color="#174a6b", marker=".", label=f"alpha={config['default_alpha_deg']:g} deg")
    ax.set_xlabel("eta = y/(b/2)")
    ax.set_ylabel("Sectional cl")
    ax.set_title("Baseline spanwise sectional lift coefficient")
    ax.grid(alpha=0.25)
    ax.legend()
    save_figure(fig, output / "baseline_spanwise_cl")

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(eta, lift, color="#237a72")
    ax.fill_between(eta, lift, color="#9dc8bd", alpha=0.4)
    ax.set_xlabel("eta = y/(b/2)")
    ax.set_ylabel("Lift per span [N/m]")
    ax.set_title("Baseline half-wing lift distribution")
    ax.grid(alpha=0.25)
    save_figure(fig, output / "baseline_lift_distribution")

    actual, reference = elliptic_data[selected][1], elliptic_data[selected][2]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(eta, actual, color="#174a6b", lw=2, label="VSPAERO baseline")
    ax.plot(eta, reference, color="#b1532f", lw=2, ls="--", label="Equal-lift elliptic reference")
    ax.set_xlabel("eta = y/(b/2)")
    ax.set_ylabel("Normalized lift distribution [1/m]")
    ax.set_title(f"Elliptic comparison at alpha={config['default_alpha_deg']:g} deg")
    ax.grid(alpha=0.25)
    ax.legend()
    save_figure(fig, output / "baseline_elliptic_comparison")
    return selected


def main():
    args = parse_args()
    project = args.project
    config = json.loads((project / "config" / "baseline_config.json").read_text(encoding="utf-8"))
    output = project / "outputs" / "baseline"
    coefficients = read_csv(output / "raw" / "baseline_vspaero_coefficients.csv")
    raw_loads = read_csv(output / "raw" / "baseline_vspaero_load_raw.csv")
    geometry = read_csv(output / "baseline_geometry_summary.csv")
    geometry_values = {row["parameter"]: row["value"] for row in geometry}
    semi_span = float(geometry_values["span_half"])
    load_rows, metrics, elliptic_data = make_load_table(raw_loads, config, semi_span)
    metrics = merge_coefficients(metrics, coefficients)
    write_csv(output / "baseline_vspaero_coefficients.csv", coefficients, ["case_id", "alpha_deg", "beta_deg", "mach", "reynolds", "CL", "CD", "CDi", "CDp", "Cm", "Cl", "Cn", "notes"])
    load_fields = ["case_id", "eta", "y", "dy", "chord", "sectional_cl", "lift_per_span", "drag_per_span", "force_x", "force_y", "force_z", "moment_x", "moment_y", "moment_z", "notes"]
    write_csv(output / "baseline_spanwise_load.csv", load_rows, load_fields)
    metric_fields = ["case_id", "CL", "CD", "CDi", "Cm", "root_bending_moment", "elliptic_error", "outer_wing_lift_fraction", "max_sectional_cl", "eta_of_max_sectional_cl"] + [f"outer_lift_fraction_eta_{value:.2f}" for value in config["outer_eta_thresholds"]] + ["notes"]
    write_csv(output / "baseline_metrics.csv", metrics, metric_fields)
    plot_planform(output)
    plot_airfoils(output)
    selected = plot_loads(output, load_rows, config, elliptic_data)
    selected_metric = next(row for row in metrics if row["case_id"] == selected)
    (output / "baseline_root_bending_moment.txt").write_text(
        "\n".join([
            f"case_id: {selected}",
            f"root_bending_moment: {number(selected_metric, 'root_bending_moment'):.6f} N m",
            "definition: integral_0^(b/2) L'(y) y dy",
            "scope: one half-wing",
            "sign: positive for upward lift",
            f"rho: {config['load_condition_rho_kg_m3']} kg/m^3",
            f"velocity: {config['load_condition_velocity_m_s']} m/s",
            f"dynamic_pressure: {0.5 * config['load_condition_rho_kg_m3'] * config['load_condition_velocity_m_s'] ** 2:.6f} Pa",
            "geometry_conversion: native OpenVSP feet converted with 0.3048 m/ft",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"Baseline post-processing complete: {output}")


if __name__ == "__main__":
    main()

