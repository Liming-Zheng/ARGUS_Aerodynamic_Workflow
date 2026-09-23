from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "baseline": "#333333",
    "washin_2deg": "#277da1",
    "washout_2deg": "#d97732",
}
LABELS = {
    "baseline": "Axis-matched baseline",
    "washin_2deg": "Wash-in +2 deg",
    "washout_2deg": "Wash-out -2 deg",
}


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    return parser.parse_args()


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def save(fig, output, name):
    output.mkdir(parents=True, exist_ok=True)
    for suffix in [".png", ".pdf", ".svg"]:
        kwargs = {"dpi": 220} if suffix == ".png" else {}
        fig.savefig(output / f"{name}{suffix}", bbox_inches="tight", **kwargs)
    plt.close(fig)


def sorted_case(rows, case_name):
    return sorted(
        (row for row in rows if row["case_name"] == case_name),
        key=lambda row: float(row["axis_x_over_c"]),
    )


def plot_aerodynamics(rows, output):
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.4))
    metrics = [
        ("CDi_reduction_vs_axis_baseline_percent", r"$C_{D_i}$ reduction [%]"),
        (
            "root_bending_change_vs_axis_baseline_percent",
            "Root bending change [%]",
        ),
        ("outer_lift_change_vs_axis_baseline_percent", "Outer-wing lift change [%]"),
        ("alpha_trim_deg", "Trim angle of attack [deg]"),
    ]
    for ax, (key, ylabel) in zip(axes.flat, metrics):
        for case_name in ["washin_2deg", "washout_2deg"]:
            cases = sorted_case(rows, case_name)
            ax.plot(
                [100.0 * float(row["axis_x_over_c"]) for row in cases],
                [float(row[key]) for row in cases],
                marker="o",
                lw=2.1,
                ms=6,
                color=COLORS[case_name],
                label=LABELS[case_name],
            )
        ax.axhline(0.0, color="#666666", lw=0.8)
        ax.set_xlabel("Rotation-axis location [% chord]")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=9)
    fig.suptitle("Fixed-lift aerodynamic sensitivity to twist-axis location")
    fig.tight_layout()
    save(fig, output, "05_axis_location_aerodynamic_sensitivity")


def plot_kinematics(rows, output):
    washin = sorted_case(rows, "washin_2deg")
    axes_x = [100.0 * float(row["axis_x_over_c"]) for row in washin]
    le = [float(row["max_le_travel_mm"]) for row in washin]
    te = [float(row["max_te_travel_mm"]) for row in washin]
    fig, ax = plt.subplots(figsize=(8.8, 5.8))
    ax.plot(axes_x, le, marker="o", lw=2.2, ms=7, label="Maximum leading-edge travel")
    ax.plot(axes_x, te, marker="s", lw=2.2, ms=7, label="Maximum trailing-edge travel")
    ax.set_xlabel("Rotation-axis location [% chord]")
    ax.set_ylabel("Rigid-section edge travel [mm]")
    ax.set_title("Geometric travel required for a +2 deg twist command")
    ax.grid(alpha=0.25)
    ax.legend()
    save(fig, output, "06_axis_location_edge_travel")


def plot_moment(rows, output):
    fig, ax = plt.subplots(figsize=(9.0, 5.8))
    for case_name in ["baseline", "washin_2deg", "washout_2deg"]:
        cases = sorted_case(rows, case_name)
        ax.plot(
            [100.0 * float(row["axis_x_over_c"]) for row in cases],
            [float(row["morph_region_abs_axis_moment_proxy_Nm"]) for row in cases],
            marker="o",
            lw=2.1,
            ms=6,
            color=COLORS[case_name],
            label=LABELS[case_name],
        )
    ax.set_xlabel("Rotation-axis location [% chord]")
    ax.set_ylabel("Integrated absolute aerodynamic moment proxy [N m]")
    ax.set_title("Aerodynamic torsional demand about the selected rotation axis")
    ax.grid(alpha=0.25)
    ax.legend()
    save(fig, output, "07_axis_location_moment_proxy")


def plot_tradeoff(rows, output):
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.4))
    for ax, case_name in zip(axes, ["washin_2deg", "washout_2deg"]):
        cases = sorted_case(rows, case_name)
        x_values = [
            float(row["root_bending_change_vs_axis_baseline_percent"])
            for row in cases
        ]
        y_values = [
            float(row["CDi_reduction_vs_axis_baseline_percent"])
            for row in cases
        ]
        ax.plot(
            x_values,
            y_values,
            marker="o",
            ms=8,
            lw=2.0,
            color=COLORS[case_name],
        )
        for index, row in enumerate(cases):
            x = float(row["root_bending_change_vs_axis_baseline_percent"])
            y = float(row["CDi_reduction_vs_axis_baseline_percent"])
            axis = 100.0 * float(row["axis_x_over_c"])
            ax.annotate(
                f"{axis:.0f}%",
                (x, y),
                xytext=(5, 7 if index % 2 == 0 else -15),
                textcoords="offset points",
                fontsize=8.5,
            )
        ax.set_xlabel("Root bending change [%]")
        ax.set_ylabel(r"$C_{D_i}$ reduction [%]")
        ax.set_title(LABELS[case_name])
        ax.grid(alpha=0.25)
        ax.margins(x=0.18, y=0.25)
    fig.suptitle(
        "Magnified drag-load sensitivity to rotation-axis location\n"
        "(labels show axis position as percent chord)"
    )
    fig.tight_layout()
    save(fig, output, "08_axis_location_drag_load_tradeoff")


def naca_thickness(x):
    return 5.0 * 0.12 * (
        0.2969 * np.sqrt(x)
        - 0.1260 * x
        - 0.3516 * x**2
        + 0.2843 * x**3
        - 0.1015 * x**4
    )


def rotate_points(x, z, axis, angle_deg):
    angle = math.radians(angle_deg)
    xr = axis + (x - axis) * math.cos(angle) - z * math.sin(angle)
    zr = (x - axis) * math.sin(angle) + z * math.cos(angle)
    return xr, zr


def plot_axis_kinematics_schematic(output):
    x = np.linspace(0.0, 1.0, 240)
    thickness = naca_thickness(x)
    outline_x = np.concatenate([x, x[::-1]])
    outline_z = np.concatenate([thickness, -thickness[::-1]])
    axes = [0.25, 0.33, 0.40, 0.50]
    colors = ["#26547c", "#2a9d8f", "#e9c46a", "#e76f51"]
    fig, panels = plt.subplots(2, 2, figsize=(11.0, 6.8), sharex=True, sharey=True)
    for panel, axis, color in zip(panels.flat, axes, colors):
        rotated_x, rotated_z = rotate_points(outline_x, outline_z, axis, 6.0)
        panel.plot(outline_x, outline_z, color="#777777", lw=1.5, label="Undeformed")
        panel.plot(rotated_x, rotated_z, color=color, lw=2.2, label="+6 deg illustration")
        panel.scatter([axis], [0.0], s=60, color="#111111", zorder=4)
        panel.axvline(axis, color="#111111", lw=0.8, ls=":")
        le_x, le_z = rotate_points(np.array([0.0]), np.array([0.0]), axis, 6.0)
        te_x, te_z = rotate_points(np.array([1.0]), np.array([0.0]), axis, 6.0)
        panel.annotate(
            "",
            xy=(le_x[0], le_z[0]),
            xytext=(0.0, 0.0),
            arrowprops={"arrowstyle": "->", "color": "#277da1", "lw": 1.5},
        )
        panel.annotate(
            "",
            xy=(te_x[0], te_z[0]),
            xytext=(1.0, 0.0),
            arrowprops={"arrowstyle": "->", "color": "#d97732", "lw": 1.5},
        )
        panel.set_title(f"Rotation axis at {100 * axis:.0f}% chord")
        panel.set_aspect("equal", adjustable="box")
        panel.grid(alpha=0.18)
        panel.set_xlim(-0.03, 1.04)
        panel.set_ylim(-0.13, 0.15)
    panels[0, 0].legend(fontsize=8, loc="upper left")
    for panel in panels[-1, :]:
        panel.set_xlabel("Normalized chord, x/c")
    for panel in panels[:, 0]:
        panel.set_ylabel("Normalized section height, z/c")
    fig.suptitle(
        "Rigid-section twist kinematics about candidate chordwise axes\n"
        "(6 deg shown only to make the displacement directions visible)"
    )
    fig.tight_layout()
    save(fig, output, "09_axis_location_section_kinematics")


def plot_engineering_trade(rows, output):
    washin = sorted_case(rows, "washin_2deg")
    axis = [100.0 * float(row["axis_x_over_c"]) for row in washin]
    base = washin[0]
    le = [
        100.0 * float(row["max_le_travel_mm"]) / float(base["max_le_travel_mm"])
        for row in washin
    ]
    te = [
        100.0 * float(row["max_te_travel_mm"]) / float(base["max_te_travel_mm"])
        for row in washin
    ]
    cdi = [
        100.0
        * float(row["CDi_reduction_vs_axis_baseline_percent"])
        / float(base["CDi_reduction_vs_axis_baseline_percent"])
        for row in washin
    ]
    fig, ax = plt.subplots(figsize=(9.4, 5.9))
    ax.plot(axis, cdi, marker="o", lw=2.0, label=r"$C_{D_i}$ benefit")
    ax.plot(axis, le, marker="^", lw=2.0, label="Leading-edge travel")
    ax.plot(axis, te, marker="D", lw=2.0, label="Trailing-edge travel")
    ax.axhline(100.0, color="#555555", lw=0.9, ls="--")
    ax.set_xlabel("Rotation-axis location [% chord]")
    ax.set_ylabel("Value relative to the 25% chord axis [%]")
    ax.set_title("Aerodynamic and kinematic consequences of moving the twist axis aft")
    ax.grid(alpha=0.25)
    ax.legend(ncol=3, fontsize=9)
    save(fig, output, "10_axis_location_normalized_engineering_trade")


def plot_spanwise_overlap(project, output):
    source = project / "outputs" / "fixed_cl_axis_sensitivity"
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.0), sharey=True)
    cases = [
        ("washin_2deg", "Wash-in +2 deg", "#277da1"),
        ("washout_2deg", "Wash-out -2 deg", "#d97732"),
    ]
    styles = [(0.25, "-"), (0.33, "--"), (0.40, "-."), (0.50, ":")]
    for panel, (case_name, title, color) in zip(axes, cases):
        for axis, style in styles:
            tag = f"x{round(100 * axis):02d}"
            case_id = f"axis_{tag}_{case_name}"
            load_rows = read_csv(source / f"{case_id}_spanwise_loads.csv")
            panel.plot(
                [float(row["eta"]) for row in load_rows],
                [float(row["lift_per_span_N_per_m"]) for row in load_rows],
                lw=2.0,
                ls=style,
                color=color,
                label=f"{100 * axis:.0f}% chord axis",
            )
        panel.axvspan(0.60, 0.95, color="#dce8df", alpha=0.45)
        panel.set_xlabel(r"Normalized span, $\eta=y/(b/2)$")
        panel.set_title(title)
        panel.grid(alpha=0.22)
        panel.legend(fontsize=8)
    axes[0].set_ylabel("Lift per span [N/m]")
    fig.suptitle(
        "Spanwise-load overlap for different chordwise rotation axes\n"
        "(all cases trimmed to the same total lift)"
    )
    fig.tight_layout()
    save(fig, output, "11_axis_location_spanwise_load_overlap")


def main():
    args = parse_args()
    source = (
        args.project
        / "outputs"
        / "fixed_cl_axis_sensitivity"
        / "fixed_cl_axis_sensitivity_summary.csv"
    )
    output = args.project / "plot" / "axis_sensitivity"
    rows = read_csv(source)
    plot_aerodynamics(rows, output)
    plot_kinematics(rows, output)
    plot_moment(rows, output)
    plot_tradeoff(rows, output)
    plot_axis_kinematics_schematic(output)
    plot_engineering_trade(rows, output)
    plot_spanwise_overlap(args.project, output)
    print(f"Wrote axis-sensitivity figures to {output}")


if __name__ == "__main__":
    main()

