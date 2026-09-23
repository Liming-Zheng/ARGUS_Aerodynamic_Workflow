"""Create the direct rigid/conventional/TE/twist comparison package."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


STATES = ["early_cruise", "late_cruise"]
CONCEPTS = ["rigid", "conventional_hinged", "trailing_edge", "twist"]
LABELS = {
    "early_cruise": "Early cruise",
    "late_cruise": "Late cruise",
    "rigid": "Rigid baseline",
    "conventional_hinged": "Conventional hinged",
    "trailing_edge": "Continuous trailing edge",
    "twist": "Distributed twist",
}
COLORS = {
    "rigid": "#4B5563",
    "conventional_hinged": "#B4473F",
    "trailing_edge": "#0076A8",
    "twist": "#D97706",
}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def number(row: dict, name: str) -> float:
    return float(row[name])


def feasible(row: dict) -> bool:
    return str(row.get("feasible", "")).lower() == "true"


def save(fig: plt.Figure, output: Path, stem: str) -> None:
    for suffix in [".png", ".svg", ".pdf"]:
        fig.savefig(
            output / f"{stem}{suffix}",
            dpi=240 if suffix == ".png" else None,
            bbox_inches="tight",
        )
    plt.close(fig)


def cruise_case_dir(cruise_project: Path, case_id: str) -> Path:
    matches = list(
        (cruise_project / "outputs" / "optimization_cases").glob(
            f"batch_*/{case_id}"
        )
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one directory for {case_id}: {matches}")
    return matches[0]


def conventional_case_dir(project: Path, case_id: str) -> Path:
    matches = list(
        (project / "outputs" / "cases").glob(f"batch_*/{case_id}")
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one directory for {case_id}: {matches}")
    return matches[0]


def select_results(project: Path, cruise_project: Path):
    rigid = {
        row["flight_state"]: row
        for row in read_rows(
            project
            / "outputs"
            / "rigid_baseline"
            / "rigid_baseline_summary.csv"
        )
    }
    conventional_rows = []
    for batch in [1, 2]:
        conventional_rows.extend(
            read_rows(
                project
                / "outputs"
                / "evaluations"
                / f"batch_{batch:02d}_results.csv"
            )
        )
    conventional = {}
    for state in STATES:
        candidates = [
            row
            for row in conventional_rows
            if row["flight_state"] == state and feasible(row)
        ]
        conventional[state] = min(candidates, key=lambda row: number(row, "CDi"))

    cruise_summary = read_rows(
        cruise_project
        / "plot"
        / "cruise_comparison"
        / "best_design_summary.csv"
    )
    morph = {
        (row["concept"], row["flight_state"]): row for row in cruise_summary
    }
    return rigid, conventional_rows, conventional, morph


def build_numeric_summary(rigid, conventional, morph):
    rows = []
    for state in STATES:
        baseline_cdi = number(rigid[state], "CDi")
        baseline_root = number(
            rigid[state], "half_wing_root_bending_moment_Nm"
        )
        root_limit = number(rigid[state], "root_bending_limit_Nm")
        rows.append(
            {
                "flight_state": state,
                "concept": "rigid",
                "case_id": rigid[state]["case_id"],
                "CDi": baseline_cdi,
                "CDi_reduction_percent": 0.0,
                "root_bending_Nm": baseline_root,
                "root_bending_utilization": baseline_root / root_limit,
                "active_constraints": (
                    "absolute_root_bending" if state == "early_cruise" else ""
                ),
            }
        )
        conv = conventional[state]
        rows.append(
            {
                "flight_state": state,
                "concept": "conventional_hinged",
                "case_id": conv["case_id"],
                "CDi": number(conv, "CDi"),
                "CDi_reduction_percent": 100.0
                * (baseline_cdi - number(conv, "CDi"))
                / baseline_cdi,
                "root_bending_Nm": number(
                    conv, "half_wing_root_bending_moment_Nm"
                ),
                "root_bending_utilization": number(
                    conv, "root_bending_utilization"
                ),
                "active_constraints": conv["active_constraints"],
                "delta_inboard_deg": number(conv, "delta_inboard_deg"),
                "delta_outboard_deg": number(conv, "delta_outboard_deg"),
                "segment_jump_deg": number(conv, "segment_jump_deg"),
                "actuator_moment_proxy_Nm": number(
                    conv, "morph_region_moment_proxy_Nm"
                ),
            }
        )
        for concept in ["trailing_edge", "twist"]:
            item = morph[(concept, state)]
            rows.append(
                {
                    "flight_state": state,
                    "concept": concept,
                    "case_id": item["case_id"],
                    "CDi": number(item, "CDi"),
                    "CDi_reduction_percent": number(
                        item, "CDi_reduction_percent"
                    ),
                    "root_bending_Nm": number(item, "root_bending_Nm"),
                    "root_bending_utilization": number(
                        item, "root_bending_utilization"
                    ),
                    "active_constraints": item["active_constraints"],
                }
            )
    return rows


def plot_numeric_bars(summary: list[dict], output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.8), constrained_layout=True)
    x = np.arange(len(CONCEPTS))
    width = 0.36
    for offset, state in zip([-width / 2, width / 2], STATES):
        subset = {
            row["concept"]: row
            for row in summary
            if row["flight_state"] == state
        }
        reductions = [
            float(subset[concept]["CDi_reduction_percent"])
            for concept in CONCEPTS
        ]
        utilizations = [
            100.0 * float(subset[concept]["root_bending_utilization"])
            for concept in CONCEPTS
        ]
        bars = axes[0].bar(
            x + offset,
            reductions,
            width,
            label=LABELS[state],
            color=[COLORS[concept] for concept in CONCEPTS],
            alpha=0.68 if state == "early_cruise" else 1.0,
            edgecolor="#1F2937",
            linewidth=0.5,
        )
        axes[0].bar_label(
            bars,
            labels=[f"{value:.2f}" for value in reductions],
            padding=3,
            fontsize=8,
        )
        axes[1].bar(
            x + offset,
            utilizations,
            width,
            label=LABELS[state],
            color=[COLORS[concept] for concept in CONCEPTS],
            alpha=0.68 if state == "early_cruise" else 1.0,
            edgecolor="#1F2937",
            linewidth=0.5,
        )
    labels = [LABELS[concept].replace(" ", "\n") for concept in CONCEPTS]
    axes[0].set_xticks(x, labels)
    axes[1].set_xticks(x, labels)
    axes[0].set_ylabel("Induced-drag reduction from rigid baseline [%]")
    axes[1].set_ylabel("Root-bending utilization [%]")
    axes[0].set_title("Aerodynamic benefit")
    axes[1].set_title("Absolute load constraint")
    axes[1].axhline(100.0, color="#9CA3AF", linestyle="--", linewidth=1.2)
    for ax in axes:
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    axes[0].legend(frameon=False, loc="best")
    fig.suptitle("Direct four-concept comparison at matched flight states")
    save(fig, output, "01_four_concept_performance")


def plot_conventional_design_space(
    conventional_rows: list[dict], rigid: dict, conventional: dict, output: Path
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8), constrained_layout=True)
    for ax, state in zip(axes, STATES):
        subset = [
            row for row in conventional_rows if row["flight_state"] == state
        ]
        reduction = [
            100.0
            * (number(rigid[state], "CDi") - number(row, "CDi"))
            / number(rigid[state], "CDi")
            for row in subset
        ]
        colors = [
            value if feasible(row) else np.nan
            for value, row in zip(reduction, subset)
        ]
        scatter = ax.scatter(
            [number(row, "delta_inboard_deg") for row in subset],
            [number(row, "delta_outboard_deg") for row in subset],
            c=colors,
            cmap="viridis",
            s=55,
            edgecolor="#1F2937",
            linewidth=0.5,
        )
        infeasible = [row for row in subset if not feasible(row)]
        ax.scatter(
            [number(row, "delta_inboard_deg") for row in infeasible],
            [number(row, "delta_outboard_deg") for row in infeasible],
            marker="x",
            s=50,
            color="#B4473F",
            label="Root-bending infeasible",
        )
        best = conventional[state]
        ax.scatter(
            [number(best, "delta_inboard_deg")],
            [number(best, "delta_outboard_deg")],
            marker="*",
            s=180,
            color="#F4C542",
            edgecolor="#111827",
            linewidth=0.8,
            label=f"Selected: {best['case_id']}",
        )
        ax.set_xlabel("Inboard aileron deflection [deg]")
        ax.set_ylabel("Outboard aileron deflection [deg]")
        ax.set_title(LABELS[state])
        ax.grid(color="#E5E7EB", linewidth=0.7)
        ax.legend(frameon=False, fontsize=8)
        fig.colorbar(scatter, ax=ax, label=r"$C_{D_i}$ reduction [%]")
    fig.suptitle("Exact conventional-control design space")
    save(fig, output, "02_conventional_design_space")


def load_best_loads(
    project: Path,
    cruise_project: Path,
    concept: str,
    state: str,
    case_id: str,
) -> list[dict]:
    if concept == "rigid":
        return read_rows(
            project
            / "outputs"
            / "rigid_baseline"
            / state
            / "spanwise_loads.csv"
        )
    if concept == "conventional_hinged":
        return read_rows(
            conventional_case_dir(project, case_id)
            / "evaluation"
            / state
            / "spanwise_loads.csv"
        )
    return read_rows(
        cruise_case_dir(cruise_project, case_id)
        / "evaluation"
        / state
        / "spanwise_loads.csv"
    )


def plot_spanwise_loads(
    project: Path, cruise_project: Path, summary: list[dict], output: Path
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), constrained_layout=True)
    for ax, state in zip(axes, STATES):
        subset = {
            row["concept"]: row
            for row in summary
            if row["flight_state"] == state
        }
        for concept in CONCEPTS:
            loads = load_best_loads(
                project,
                cruise_project,
                concept,
                state,
                subset[concept]["case_id"],
            )
            ax.plot(
                [number(row, "eta") for row in loads],
                [number(row, "lift_per_span_N_per_m") for row in loads],
                color=COLORS[concept],
                linewidth=1.9,
                linestyle="--" if concept == "rigid" else "-",
                label=LABELS[concept],
            )
        ax.axvspan(0.60, 1.00, color="#D1FAE5", alpha=0.25)
        ax.set_title(LABELS[state])
        ax.set_xlabel(r"Semi-span coordinate $\eta$")
        ax.set_ylabel("Lift per unit span [N/m]")
        ax.grid(color="#E5E7EB", linewidth=0.7)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Best feasible spanwise loading")
    save(fig, output, "03_four_concept_spanwise_lift")


def plot_geometry_definition(config: dict, output: Path) -> None:
    settings = config["conventional_control"]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4), constrained_layout=True)
    ax = axes[0]
    eta = np.array([0.0, 0.383, 0.71, 0.852, 0.97, 1.0])
    leading = 0.28 * eta
    trailing = 1.0 - 0.55 * eta
    ax.plot(eta, leading, color="#1F2937", linewidth=2)
    ax.plot(eta, trailing, color="#1F2937", linewidth=2)
    for segment, color in zip(settings["segments"], ["#B4473F", "#D97706"]):
        start = float(segment["eta_start"])
        end = float(segment["eta_end"])
        grid = np.linspace(start, end, 60)
        te = 1.0 - 0.55 * grid
        le = 0.28 * grid
        hinge = le + float(settings["hinge_x_over_c"]) * (te - le)
        ax.fill_between(grid, hinge, te, color=color, alpha=0.65)
        ax.text(
            0.5 * (start + end),
            np.interp(0.5 * (start + end), grid, 0.5 * (hinge + te)),
            segment["name"].replace("low_speed_aileron_", ""),
            ha="center",
            va="center",
            fontsize=8,
            color="white",
            fontweight="bold",
        )
    ax.set_xlim(0, 1.02)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(r"Semi-span coordinate $\eta$")
    ax.set_ylabel("Schematic chordwise coordinate")
    ax.set_title("NASA AR=12 low-speed aileron layout")
    ax.grid(color="#E5E7EB", linewidth=0.6)

    ax = axes[1]
    x = np.linspace(0.0, 1.0, 300)
    baseline = 0.07 * np.sin(np.pi * x) * (1.0 - 0.35 * x)
    hinge = float(settings["hinge_x_over_c"])
    command = 6.6544
    theta = np.radians(-command)
    y_h = np.interp(hinge, x, baseline)
    deformed_x = x.copy()
    deformed_y = baseline.copy()
    mask = x > hinge
    dx = x[mask] - hinge
    dy = baseline[mask] - y_h
    deformed_x[mask] = hinge + dx * np.cos(theta) - dy * np.sin(theta)
    deformed_y[mask] = y_h + dx * np.sin(theta) + dy * np.cos(theta)
    ax.plot(x, baseline, "--", color=COLORS["rigid"], label="Neutral section")
    ax.plot(
        deformed_x,
        deformed_y,
        color=COLORS["conventional_hinged"],
        linewidth=2.2,
        label=r"Hinged, $\delta=+6.65^\circ$",
    )
    ax.scatter([hinge], [y_h], color="#111827", s=32, zorder=4)
    ax.axvline(hinge, color="#9CA3AF", linestyle=":", linewidth=1)
    ax.text(hinge + 0.01, y_h + 0.015, r"$x_h/c=0.70$", fontsize=9)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(r"$x/c$")
    ax.set_ylabel(r"$z/c$")
    ax.set_title("Zero-gap hinged-section representation")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(color="#E5E7EB", linewidth=0.6)
    save(fig, output, "04_conventional_geometry_definition")


def adaptation_summary(
    project: Path,
    cruise_project: Path,
    conventional_rows: list[dict],
    conventional: dict,
) -> list[dict]:
    rows = [{"concept": "rigid", "late_cruise_adaptation_benefit_percent": 0.0}]
    early_id = conventional["early_cruise"]["case_id"]
    early_at_late = next(
        row
        for row in conventional_rows
        if row["case_id"] == early_id and row["flight_state"] == "late_cruise"
    )
    late = conventional["late_cruise"]
    rows.append(
        {
            "concept": "conventional_hinged",
            "early_optimized_case": early_id,
            "late_optimized_case": late["case_id"],
            "late_cruise_adaptation_benefit_percent": 100.0
            * (number(early_at_late, "CDi") - number(late, "CDi"))
            / number(early_at_late, "CDi"),
        }
    )
    morph_rows = read_rows(
        cruise_project
        / "plot"
        / "cruise_comparison"
        / "cross_state_adaptation.csv"
    )
    rows.extend(morph_rows)
    return rows


def plot_adaptation(rows: list[dict], output: Path) -> None:
    values = {
        row["concept"]: float(row["late_cruise_adaptation_benefit_percent"])
        for row in rows
    }
    fig, ax = plt.subplots(figsize=(9.2, 4.8), constrained_layout=True)
    bars = ax.bar(
        np.arange(len(CONCEPTS)),
        [values[concept] for concept in CONCEPTS],
        color=[COLORS[concept] for concept in CONCEPTS],
        edgecolor="#1F2937",
        linewidth=0.6,
    )
    ax.bar_label(
        bars,
        labels=[f"{values[concept]:.2f}%" for concept in CONCEPTS],
        padding=4,
    )
    ax.set_xticks(
        np.arange(len(CONCEPTS)),
        [LABELS[concept].replace(" ", "\n") for concept in CONCEPTS],
    )
    ax.set_ylabel("Benefit of changing from early- to late-optimized shape [%]")
    ax.set_title("Late-cruise benefit of mission adaptation")
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    save(fig, output, "05_four_concept_adaptation")


def qualitative_matrix() -> list[dict]:
    return [
        {
            "metric": "Outer-mold-line continuity",
            "rigid": "Continuous",
            "conventional_hinged": "Discrete hinges/gaps",
            "trailing_edge": "Continuous camber",
            "twist": "Continuous section rotation",
        },
        {
            "metric": "Spanwise load-shaping authority",
            "rigid": "None",
            "conventional_hinged": "Low: 2 segments",
            "trailing_edge": "High: 5 controls",
            "twist": "High: 5 controls",
        },
        {
            "metric": "Actuation/local mechanism",
            "rigid": "None",
            "conventional_hinged": "Mature local hinges",
            "trailing_edge": "Distributed aft-chord mechanism",
            "twist": "Whole-section torsion mechanism",
        },
        {
            "metric": "Structural integration risk",
            "rigid": "Lowest",
            "conventional_hinged": "Low",
            "trailing_edge": "Medium",
            "twist": "Highest",
        },
        {
            "metric": "Technology maturity",
            "rigid": "Highest",
            "conventional_hinged": "Highest",
            "trailing_edge": "Low/medium",
            "twist": "Low/medium",
        },
        {
            "metric": "Gap/noise concern",
            "rigid": "None",
            "conventional_hinged": "Present",
            "trailing_edge": "Reduced",
            "twist": "Reduced",
        },
        {
            "metric": "Current evidence",
            "rigid": "VSPAERO baseline",
            "conventional_hinged": "40 exact geometries",
            "trailing_edge": "DOE + surrogate + exact",
            "twist": "DOE + surrogate + exact",
        },
    ]


def write_markdown(
    output: Path, summary: list[dict], adaptation: list[dict]
) -> None:
    lookup = {
        (row["concept"], row["flight_state"]): row for row in summary
    }
    adap = {
        row["concept"]: float(row["late_cruise_adaptation_benefit_percent"])
        for row in adaptation
    }
    lines = [
        "# Four-concept comparison summary",
        "",
        "## Exact aerodynamic results",
        "",
        "| Concept | Early CDi reduction | Late CDi reduction | Early root utilization | Late root utilization | Late adaptation benefit |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for concept in CONCEPTS:
        early = lookup[(concept, "early_cruise")]
        late = lookup[(concept, "late_cruise")]
        lines.append(
            f"| {LABELS[concept]} | "
            f"{float(early['CDi_reduction_percent']):.3f}% | "
            f"{float(late['CDi_reduction_percent']):.3f}% | "
            f"{100*float(early['root_bending_utilization']):.2f}% | "
            f"{100*float(late['root_bending_utilization']):.2f}% | "
            f"{adap[concept]:.3f}% |"
        )
    lines.extend(
        [
            "",
            "## Decision interpretation",
            "",
            "- The conventional hinged benchmark is deliberately based on the NASA AR=12 low-speed aileron geometry: two 30%-chord segments over eta=0.710...0.970.",
            "- At early cruise, the absolute root-bending constraint removes the useful conventional deflections; its optimum is the neutral wing.",
            "- At late cruise, the conventional system recovers part of the drag benefit, but its two discrete segments provide less load-shaping authority than either continuous concept.",
            "- Continuous trailing-edge morphing gives the strongest late-cruise drag reduction in the present dataset.",
            "- Distributed twist gives the strongest early-cruise improvement and slightly stronger two-point average aerodynamic benefit, but requires the most demanding structural/torsional mechanism.",
            "- The aerodynamic evidence therefore supports twist as the primary high-authority concept and trailing-edge camber as the strongest late-cruise concept. Final down-selection still requires actuator mass, power, rate, stiffness, and aeroelastic evidence.",
            "",
            "The conventional VSPAERO geometry is a zero-gap representation. Real hinge gaps and viscous/profile-drag penalties are not included, so its aerodynamic result is optimistic.",
        ]
    )
    (output / "RESULTS_SUMMARY_CN_EN.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def copy_final_geometries(
    project: Path, conventional: dict, output: Path
) -> None:
    target = output / "final_geometries"
    target.mkdir(parents=True, exist_ok=True)
    copied = {}
    for state in STATES:
        row = conventional[state]
        source = (
            conventional_case_dir(project, row["case_id"])
            / f"{row['case_id']}.vsp3"
        )
        destination = target / f"best_conventional_{state}_{row['case_id']}.vsp3"
        shutil.copy2(source, destination)
        copied[state] = str(destination)
    (target / "geometry_manifest.json").write_text(
        json.dumps(copied, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    cruise_project = project.parent / "argus_cruise_comparison"
    output = project / "plot" / "four_concept_comparison"
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    rigid, conventional_rows, conventional, morph = select_results(
        project, cruise_project
    )
    summary = build_numeric_summary(rigid, conventional, morph)
    write_csv(output / "four_concept_numeric_summary.csv", summary)
    plot_numeric_bars(summary, output)
    plot_conventional_design_space(
        conventional_rows, rigid, conventional, output
    )
    plot_spanwise_loads(project, cruise_project, summary, output)
    plot_geometry_definition(config, output)
    adaptation = adaptation_summary(
        project, cruise_project, conventional_rows, conventional
    )
    write_csv(output / "four_concept_adaptation.csv", adaptation)
    plot_adaptation(adaptation, output)
    write_csv(output / "qualitative_decision_matrix.csv", qualitative_matrix())
    copy_final_geometries(project, conventional, output)
    write_markdown(output, summary, adaptation)
    (output / "selected_cases.json").write_text(
        json.dumps(
            {
                row["concept"] + "_" + row["flight_state"]: row["case_id"]
                for row in summary
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote direct comparison package to {output}")


if __name__ == "__main__":
    main()

