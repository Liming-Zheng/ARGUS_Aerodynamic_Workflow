"""Create editable concept-level schematics for the ARGUS report.

The figures deliberately use a common visual language:

- gray: fixed or baseline structure;
- red: conventional hinged control;
- blue: continuous trailing-edge camber morphing;
- orange: distributed twist morphing;
- green: the active outer-wing interval.

Every figure is written as SVG, PDF, and PNG.
"""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Arc, FancyArrowPatch, FancyBboxPatch, Polygon


COLORS = {
    "fixed": "#4B5563",
    "outline": "#1F2937",
    "hinged": "#B4473F",
    "trailing_edge": "#0076A8",
    "twist": "#D97706",
    "active": "#3A7D5D",
    "light": "#E5E7EB",
    "pale_green": "#DCEADF",
}


def save(fig: plt.Figure, output: Path, stem: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for suffix in [".png", ".svg", ".pdf"]:
        fig.savefig(
            output / f"{stem}{suffix}",
            dpi=260 if suffix == ".png" else None,
            bbox_inches="tight",
            facecolor="white",
        )
    plt.close(fig)


def wing_edges(eta):
    eta = np.asarray(eta, dtype=float)
    leading = 0.37 + 0.23 * eta
    trailing = 0.54 + 0.12 * eta
    return leading, trailing


def reference_planform_edges(eta):
    """Return equal-scale streamwise coordinates for the refined AR=12 wing."""
    eta = np.asarray(eta, dtype=float)
    section_eta = np.array(
        [
            0.0000, 0.0960, 0.3830, 0.4500, 0.5150, 0.5475, 0.5800,
            0.6125, 0.6450, 0.6775, 0.7100, 0.7455, 0.7810, 0.8165,
            0.8520, 0.8820, 0.9260, 0.9700, 1.0000,
        ]
    )
    section_chord = np.array(
        [
            2.1000, 1.8450, 1.1167, 1.0497, 0.9847, 0.9522, 0.9197,
            0.8872, 0.8547, 0.8222, 0.7897, 0.7554, 0.7210, 0.6867,
            0.6523, 0.6233, 0.5808, 0.5383, 0.5000,
        ]
    )
    semispan = 6.0
    sweep_deg = 28.86199
    leading = eta * np.tan(np.deg2rad(sweep_deg))
    chord = np.interp(eta, section_eta, section_chord) / semispan
    trailing = leading + chord
    return leading, trailing


def half_wing_polygon(sign: float) -> np.ndarray:
    eta = np.array([0.0, 1.0])
    leading, trailing = wing_edges(eta)
    return np.array(
        [
            [leading[0], sign * 0.045],
            [leading[1], sign * 0.43],
            [trailing[1], sign * 0.43],
            [trailing[0], sign * 0.045],
        ]
    )


def region_polygon(eta_start: float, eta_end: float, x_start: float) -> np.ndarray:
    eta = np.array([eta_start, eta_end])
    leading, trailing = wing_edges(eta)
    start = leading + x_start * (trailing - leading)
    return np.array(
        [
            [start[0], eta[0] * 0.43],
            [start[1], eta[1] * 0.43],
            [trailing[1], eta[1] * 0.43],
            [trailing[0], eta[0] * 0.43],
        ]
    )


def whole_chord_region(eta_start: float, eta_end: float) -> np.ndarray:
    eta = np.array([eta_start, eta_end])
    leading, trailing = wing_edges(eta)
    return np.array(
        [
            [leading[0], eta[0] * 0.43],
            [leading[1], eta[1] * 0.43],
            [trailing[1], eta[1] * 0.43],
            [trailing[0], eta[0] * 0.43],
        ]
    )


def mirror(polygon: np.ndarray) -> np.ndarray:
    result = polygon.copy()
    result[:, 1] *= -1.0
    return result


def draw_aircraft(ax, concept: str) -> None:
    for sign in [-1.0, 1.0]:
        ax.add_patch(
            Polygon(
                half_wing_polygon(sign),
                closed=True,
                facecolor="#F3F4F6",
                edgecolor=COLORS["outline"],
                linewidth=1.2,
                zorder=1,
            )
        )
    fuselage = np.array(
        [
            [0.05, 0.0],
            [0.11, 0.033],
            [0.30, 0.044],
            [0.73, 0.035],
            [0.96, 0.014],
            [1.00, 0.0],
            [0.96, -0.014],
            [0.73, -0.035],
            [0.30, -0.044],
            [0.11, -0.033],
        ]
    )
    tail_right = np.array(
        [[0.78, 0.02], [0.91, 0.18], [0.96, 0.18], [0.91, 0.015]]
    )
    ax.add_patch(
        Polygon(
            tail_right,
            closed=True,
            facecolor="#F3F4F6",
            edgecolor=COLORS["outline"],
            linewidth=1.0,
        )
    )
    ax.add_patch(
        Polygon(
            mirror(tail_right),
            closed=True,
            facecolor="#F3F4F6",
            edgecolor=COLORS["outline"],
            linewidth=1.0,
        )
    )
    ax.add_patch(
        Polygon(
            fuselage,
            closed=True,
            facecolor="white",
            edgecolor=COLORS["outline"],
            linewidth=1.3,
            zorder=5,
        )
    )

    if concept == "conventional_hinged":
        segments = [(0.710, 0.852), (0.852, 0.970)]
        for eta_start, eta_end in segments:
            polygon = region_polygon(eta_start, eta_end, 0.70)
            for item in [polygon, mirror(polygon)]:
                ax.add_patch(
                    Polygon(
                        item,
                        closed=True,
                        facecolor=COLORS["hinged"],
                        edgecolor="white",
                        linewidth=0.9,
                        alpha=0.88,
                        zorder=3,
                    )
                )
    elif concept == "trailing_edge":
        polygon = region_polygon(0.60, 1.00, 0.62)
        for item in [polygon, mirror(polygon)]:
            ax.add_patch(
                Polygon(
                    item,
                    closed=True,
                    facecolor=COLORS["trailing_edge"],
                    edgecolor="none",
                    alpha=0.82,
                    zorder=3,
                )
            )
        for sign in [-1, 1]:
            ax.annotate(
                "",
                xy=(0.69, sign * 0.36),
                xytext=(0.64, sign * 0.30),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=COLORS["trailing_edge"],
                    linewidth=1.5,
                    connectionstyle="arc3,rad=0.25",
                ),
            )
    elif concept == "twist":
        polygon = whole_chord_region(0.60, 1.00)
        for item in [polygon, mirror(polygon)]:
            ax.add_patch(
                Polygon(
                    item,
                    closed=True,
                    facecolor=COLORS["twist"],
                    edgecolor="none",
                    alpha=0.55,
                    zorder=2,
                )
            )
        for sign in [-1, 1]:
            for eta in [0.68, 0.80, 0.92]:
                leading, trailing = wing_edges([eta])
                x = float(leading[0] + 0.25 * (trailing[0] - leading[0]))
                y = sign * eta * 0.43
                ax.add_patch(
                    Arc(
                        (x, y),
                        0.055,
                        0.045,
                        theta1=35 if sign > 0 else 205,
                        theta2=285 if sign > 0 else 455,
                        color=COLORS["twist"],
                        linewidth=1.3,
                        zorder=6,
                    )
                )
    ax.set_xlim(0.02, 1.02)
    ax.set_ylim(-0.48, 0.48)
    ax.set_aspect("equal")
    ax.axis("off")


def four_concept_aircraft(output: Path) -> None:
    concepts = [
        ("rigid", "Rigid reference", "No adaptive geometry"),
        (
            "conventional_hinged",
            "Conventional hinged",
            "Two discrete 30%-chord aileron segments",
        ),
        (
            "trailing_edge",
            "Continuous trailing edge",
            r"Camber change aft of $x_h/c=0.62$",
        ),
        (
            "twist",
            "Distributed twist",
            r"Whole sections rotate about $x_a/c=0.25$",
        ),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.4, 7.1), constrained_layout=True)
    for ax, (concept, title, subtitle) in zip(axes.flat, concepts):
        draw_aircraft(ax, concept)
        ax.set_title(title, fontsize=13, fontweight="bold", pad=3)
        ax.text(
            0.5,
            -0.04,
            subtitle,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9,
            color=COLORS["fixed"],
        )
    fig.suptitle(
        "ARGUS concept map: what changes on the aircraft?",
        fontsize=16,
        fontweight="bold",
    )
    save(fig, output, "01_four_concept_aircraft_overview")


def base_camber(x):
    return 0.055 * np.sin(np.pi * x) * (1.0 - 0.20 * x)


def rotate_curve(x, z, axis_x, axis_z, angle_deg):
    theta = radians(angle_deg)
    dx = x - axis_x
    dz = z - axis_z
    return (
        axis_x + dx * cos(theta) - dz * sin(theta),
        axis_z + dx * sin(theta) + dz * cos(theta),
    )


def section_kinematics(output: Path) -> None:
    x = np.linspace(0, 1, 401)
    baseline = base_camber(x)
    fig, axes = plt.subplots(3, 1, figsize=(10.8, 8.3), constrained_layout=True)

    ax = axes[0]
    hinge = 0.70
    z_hinge = float(base_camber(np.array([hinge]))[0])
    x_hinged, z_hinged = x.copy(), baseline.copy()
    mask = x >= hinge
    x_hinged[mask], z_hinged[mask] = rotate_curve(
        x[mask], baseline[mask], hinge, z_hinge, -7.0
    )
    ax.plot(x, baseline, "--", color=COLORS["fixed"], label="Baseline")
    ax.plot(
        x_hinged,
        z_hinged,
        color=COLORS["hinged"],
        linewidth=2.4,
        label="Deflected shape",
    )
    ax.scatter([hinge], [z_hinge], color=COLORS["outline"], s=28, zorder=4)
    ax.axvline(hinge, color=COLORS["light"], linewidth=1.0)
    ax.text(0.02, 0.86, "A  Conventional hinge", transform=ax.transAxes, fontweight="bold")
    ax.text(
        0.02,
        0.66,
        "Rigid aft segment; slope changes abruptly at the hinge",
        transform=ax.transAxes,
        fontsize=9,
        color=COLORS["fixed"],
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.88, pad=1.5),
    )
    ax.annotate(
        r"$x_h/c=0.70$",
        xy=(hinge, z_hinge),
        xytext=(0.57, -0.035),
        arrowprops=dict(arrowstyle="->", color=COLORS["outline"]),
        fontsize=9,
    )

    ax = axes[1]
    xh = 0.62
    amplitude = 0.045
    morphed = baseline.copy()
    active = x >= xh
    xi = (x[active] - xh) / (1.0 - xh)
    morphed[active] -= amplitude * (3 * xi**2 - 2 * xi**3)
    ax.plot(x, baseline, "--", color=COLORS["fixed"], label="Baseline")
    ax.plot(
        x,
        morphed,
        color=COLORS["trailing_edge"],
        linewidth=2.4,
        label="Morphed shape",
    )
    ax.axvspan(xh, 1.0, color=COLORS["trailing_edge"], alpha=0.08)
    ax.axvline(xh, color=COLORS["trailing_edge"], linestyle=":", linewidth=1.2)
    ax.text(0.02, 0.86, "B  Continuous trailing edge", transform=ax.transAxes, fontweight="bold")
    ax.text(
        0.02,
        0.66,
        "Forward airfoil is fixed; aft camber changes smoothly",
        transform=ax.transAxes,
        fontsize=9,
        color=COLORS["fixed"],
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.88, pad=1.5),
    )
    ax.annotate(
        r"$x_h/c=0.62$",
        xy=(xh, float(base_camber(np.array([xh]))[0])),
        xytext=(0.50, -0.035),
        arrowprops=dict(arrowstyle="->", color=COLORS["trailing_edge"]),
        fontsize=9,
    )

    ax = axes[2]
    axis = 0.25
    z_axis = float(base_camber(np.array([axis]))[0])
    x_twist, z_twist = rotate_curve(x, baseline, axis, z_axis, 4.0)
    ax.plot(x, baseline, "--", color=COLORS["fixed"], label="Baseline")
    ax.plot(
        x_twist,
        z_twist,
        color=COLORS["twist"],
        linewidth=2.4,
        label="Twisted section",
    )
    ax.scatter([axis], [z_axis], color=COLORS["outline"], s=28, zorder=4)
    ax.add_patch(
        Arc(
            (axis, z_axis),
            0.16,
            0.075,
            theta1=15,
            theta2=315,
            color=COLORS["twist"],
            linewidth=1.5,
        )
    )
    ax.text(0.02, 0.86, "C  Distributed twist", transform=ax.transAxes, fontweight="bold")
    ax.text(
        0.02,
        0.66,
        "Airfoil profile is unchanged; the whole section incidence changes",
        transform=ax.transAxes,
        fontsize=9,
        color=COLORS["fixed"],
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.88, pad=1.5),
    )
    ax.annotate(
        r"$x_a/c=0.25$",
        xy=(axis, z_axis),
        xytext=(0.12, -0.035),
        arrowprops=dict(arrowstyle="->", color=COLORS["twist"]),
        fontsize=9,
    )

    for index, ax in enumerate(axes):
        ax.set_xlim(-0.02, 1.04)
        ax.set_ylim(-0.075, 0.105)
        ax.set_aspect(2.2)
        ax.grid(color="#EEF0F2", linewidth=0.7)
        ax.set_ylabel(r"$z/c$")
        if index == 2:
            ax.set_xlabel(r"$x/c$")
        ax.legend(frameon=False, loc="lower left", ncol=2, fontsize=8)
    fig.suptitle(
        "Three deformation mechanisms used in the aerodynamic models",
        fontsize=15,
        fontweight="bold",
    )
    save(fig, output, "02_section_kinematics_comparison")


def parameterization_map(output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), constrained_layout=True)
    control_etas = np.array([0.68, 0.76, 0.84, 0.92, 1.00])

    ax = axes[0]
    eta = np.linspace(0, 1, 200)
    leading, trailing = reference_planform_edges(eta)
    ax.plot(eta, leading, color=COLORS["outline"], linewidth=1.8)
    ax.plot(eta, trailing, color=COLORS["outline"], linewidth=1.8)
    ax.fill_between(
        eta,
        leading,
        trailing,
        where=eta <= 0.60,
        color=COLORS["light"],
        alpha=0.75,
        label="Fixed inner wing",
    )
    te_start = leading + 0.62 * (trailing - leading)
    ax.fill_between(
        eta,
        te_start,
        trailing,
        where=eta >= 0.60,
        color=COLORS["trailing_edge"],
        alpha=0.60,
        label="Continuous camber region",
    )
    for index, station in enumerate(control_etas, start=1):
        le = float(np.interp(station, eta, leading))
        te = float(np.interp(station, eta, trailing))
        ax.plot([station, station], [le, te], color="white", linewidth=1.0)
        ax.scatter([station], [te + 0.020], color=COLORS["trailing_edge"], s=26)
        ax.text(station, te + 0.042, f"$A_{index}$", ha="center", fontsize=8)
    ax.axvline(0.60, color=COLORS["active"], linestyle="--", linewidth=1.2)
    ax.set_title("Continuous trailing-edge variables")
    ax.set_xlabel(r"Semi-span coordinate $y/(b/2)$")
    ax.set_ylabel(r"Streamwise coordinate $x/(b/2)$")
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    ax = axes[1]
    ax.plot(eta, leading, color=COLORS["outline"], linewidth=1.8)
    ax.plot(eta, trailing, color=COLORS["outline"], linewidth=1.8)
    ax.fill_between(
        eta,
        leading,
        trailing,
        where=eta <= 0.60,
        color=COLORS["light"],
        alpha=0.75,
        label="Fixed inner wing",
    )
    ax.fill_between(
        eta,
        leading,
        trailing,
        where=eta >= 0.60,
        color=COLORS["twist"],
        alpha=0.48,
        label="Rotating outer sections",
    )
    axis_line = leading + 0.25 * (trailing - leading)
    ax.plot(
        eta[eta >= 0.60],
        axis_line[eta >= 0.60],
        color=COLORS["outline"],
        linestyle="--",
        linewidth=1.2,
        label=r"Rotation axis $x_a/c=0.25$",
    )
    for index, station in enumerate(control_etas, start=1):
        le = float(np.interp(station, eta, leading))
        te = float(np.interp(station, eta, trailing))
        ax.plot([station, station], [le, te], color="white", linewidth=1.0)
        ax.scatter([station], [te + 0.020], color=COLORS["twist"], s=26)
        ax.text(
            station,
            te + 0.042,
            rf"$\Delta\theta_{index}$",
            ha="center",
            fontsize=8,
        )
    ax.axvline(0.60, color=COLORS["active"], linestyle="--", linewidth=1.2)
    ax.set_title("Distributed-twist variables")
    ax.set_xlabel(r"Semi-span coordinate $y/(b/2)$")
    ax.set_ylabel(r"Streamwise coordinate $x/(b/2)$")
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    for ax in axes:
        ax.set_xlim(-0.02, 1.04)
        ax.set_ylim(-0.04, 0.68)
        ax.invert_yaxis()
        ax.set_aspect("equal", adjustable="box")
        ax.grid(color="#EEF0F2", linewidth=0.7)
    fig.suptitle(
        "How five optimization commands map onto the OpenVSP wing",
        fontsize=15,
        fontweight="bold",
    )
    save(fig, output, "03_spanwise_parameterization_map")


def mission_adaptation(output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.4), constrained_layout=True)
    states = [
        (
            "Early cruise",
            "74,500 kg equivalent lift\n10 km, Mach 0.78",
            1.00,
            0.479,
            "Root-bending constraint active",
        ),
        (
            "Late cruise",
            "56,000 kg equivalent lift\n12 km, Mach 0.78",
            0.75,
            2.628,
            "Root-bending margin available",
        ),
    ]
    for ax, (title, condition, load_scale, best_reduction, note) in zip(
        axes, states
    ):
        draw_aircraft(ax, "twist" if title.startswith("Early") else "trailing_edge")
        eta = np.linspace(0.08, 0.95, 8)
        leading, _ = wing_edges(eta)
        for sign in [-1, 1]:
            for station, x_le in zip(eta, leading):
                length = 0.075 * load_scale * np.sqrt(max(0.0, 1 - station**2))
                y = sign * station * 0.43
                ax.annotate(
                    "",
                    xy=(x_le - length, y),
                    xytext=(x_le, y),
                    arrowprops=dict(
                        arrowstyle="-|>",
                        color=COLORS["active"],
                        linewidth=1.0,
                        alpha=0.9,
                    ),
                )
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.text(
            0.5,
            0.98,
            condition,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9,
            color=COLORS["fixed"],
        )
        ax.text(
            0.5,
            -0.02,
            note,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9,
            fontweight="bold",
            color=COLORS["outline"],
        )
        ax.text(
            0.5,
            -0.11,
            f"Best continuous-concept $C_{{D_i}}$ reduction: {best_reduction:.3f}%",
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9,
        )
    fig.suptitle(
        "Why the wing needs different shapes during cruise",
        fontsize=16,
        fontweight="bold",
    )
    save(fig, output, "04_early_late_mission_adaptation")


def study_evidence_map(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(11.6, 4.3), constrained_layout=True)
    stages = [
        (
            "1  Reference and workflow",
            "NASA/OpenVSP AR=12 wing\n$M=0.1$, fixed $C_L$\nGeometry, trim and load extraction",
            COLORS["fixed"],
        ),
        (
            "2  Trailing-edge development",
            "Outer-wing camber morphing\nPure $C_{D_i}$ plus constraints\nStrict candidate: mbr_c01_l011",
            COLORS["trailing_edge"],
        ),
        (
            "3  Twist development",
            "DOE, five-variable optimization\nQuarter-chord axis study\nBidirectional load authority",
            COLORS["twist"],
        ),
        (
            "4  Current decision study",
            "Mach 0.78 early/late cruise\nRigid, hinged, camber and twist\nMatched lift and bending limit",
            COLORS["active"],
        ),
    ]
    x_positions = np.linspace(0.02, 0.77, len(stages))
    box_width = 0.21
    box_height = 0.55
    y = 0.29
    for index, ((title, body, color), x) in enumerate(zip(stages, x_positions)):
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                box_width,
                box_height,
                boxstyle="round,pad=0.012,rounding_size=0.012",
                linewidth=1.5,
                edgecolor=color,
                facecolor="white",
            )
        )
        ax.add_patch(
            FancyBboxPatch(
                (x, y + box_height - 0.12),
                box_width,
                0.12,
                boxstyle="round,pad=0.012,rounding_size=0.012",
                linewidth=0,
                facecolor=color,
                alpha=0.14,
            )
        )
        ax.text(
            x + box_width / 2,
            y + box_height - 0.06,
            title,
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=COLORS["outline"],
        )
        ax.text(
            x + box_width / 2,
            y + 0.21,
            body,
            ha="center",
            va="center",
            fontsize=8.5,
            linespacing=1.35,
            color=COLORS["fixed"],
        )
        if index < len(stages) - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (x + box_width + 0.01, y + box_height / 2),
                    (x_positions[index + 1] - 0.01, y + box_height / 2),
                    arrowstyle="-|>",
                    mutation_scale=12,
                    linewidth=1.2,
                    color=COLORS["outline"],
                )
            )
    ax.text(
        0.5,
        0.11,
        "Interpret results within their stage: operating points and constraints "
        "change between workflow development and the current decision study.",
        ha="center",
        va="center",
        fontsize=9.5,
        fontweight="bold",
        color=COLORS["outline"],
        bbox=dict(
            boxstyle="round,pad=0.45",
            facecolor=COLORS["pale_green"],
            edgecolor=COLORS["active"],
            linewidth=1.0,
        ),
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.suptitle(
        "How the evidence in this report builds toward the concept decision",
        fontsize=15,
        fontweight="bold",
    )
    save(fig, output, "05_study_evidence_map")


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    output = project / "plot" / "report_explainers"
    four_concept_aircraft(output)
    section_kinematics(output)
    parameterization_map(output)
    mission_adaptation(output)
    study_evidence_map(output)
    print(f"Wrote report explainer figures to {output}")


if __name__ == "__main__":
    main()

