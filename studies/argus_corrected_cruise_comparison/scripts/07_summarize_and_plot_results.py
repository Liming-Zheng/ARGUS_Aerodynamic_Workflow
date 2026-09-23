"""Summarize the two-state cruise optimization and create report-ready plots."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


STATES = ["early_cruise", "late_cruise"]
CONCEPTS = ["trailing_edge", "twist"]
LABELS = {
    "early_cruise": "Early cruise",
    "late_cruise": "Late cruise",
    "trailing_edge": "Trailing-edge camber",
    "twist": "Distributed twist",
}
COLORS = {
    "baseline": "#4B5563",
    "trailing_edge": "#0076A8",
    "twist": "#D97706",
    "limit": "#9CA3AF",
}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def as_float(row: dict, name: str) -> float:
    return float(row[name])


def is_feasible(row: dict) -> bool:
    return str(row.get("feasible", "")).lower() == "true"


def save_figure(fig: plt.Figure, output: Path, stem: str) -> None:
    for suffix in [".png", ".svg", ".pdf"]:
        fig.savefig(
            output / f"{stem}{suffix}",
            dpi=240 if suffix == ".png" else None,
            bbox_inches="tight",
        )
    plt.close(fig)


def find_case_dir(project: Path, case_id: str) -> Path:
    matches = list(
        (project / "outputs" / "optimization_cases").glob(
            f"batch_*/{case_id}"
        )
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one directory for {case_id}: {matches}")
    return matches[0]


def best_rows(
    rows: list[dict], baseline: dict[str, dict]
) -> tuple[dict[tuple[str, str], dict], list[dict]]:
    selected: dict[tuple[str, str], dict] = {}
    summary: list[dict] = []
    for state in STATES:
        baseline_cdi = as_float(baseline[state], "CDi")
        for concept in CONCEPTS:
            candidates = [
                row
                for row in rows
                if row["flight_state"] == state
                and row["concept"] == concept
                and is_feasible(row)
            ]
            best = min(candidates, key=lambda row: as_float(row, "CDi"))
            selected[(concept, state)] = best
            summary.append(
                {
                    "flight_state": state,
                    "concept": concept,
                    "case_id": best["case_id"],
                    "CDi": as_float(best, "CDi"),
                    "baseline_CDi": baseline_cdi,
                    "CDi_reduction_percent": 100.0
                    * (baseline_cdi - as_float(best, "CDi"))
                    / baseline_cdi,
                    "root_bending_Nm": as_float(
                        best, "half_wing_root_bending_moment_Nm"
                    ),
                    "root_bending_utilization": as_float(
                        best, "root_bending_utilization"
                    ),
                    "CL_error": as_float(best, "CL_error"),
                    "active_constraints": best["active_constraints"],
                }
            )
    return selected, summary


def plot_reduction(summary: list[dict], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 5.2), constrained_layout=True)
    x = np.arange(len(STATES))
    width = 0.30
    for offset, concept in zip([-width / 2, width / 2], CONCEPTS):
        values = [
            next(
                row["CDi_reduction_percent"]
                for row in summary
                if row["flight_state"] == state
                and row["concept"] == concept
            )
            for state in STATES
        ]
        bars = ax.bar(
            x + offset,
            values,
            width,
            color=COLORS[concept],
            edgecolor="#1F2937",
            linewidth=0.6,
            label=LABELS[concept],
        )
        ax.bar_label(
            bars,
            labels=[f"{value:.2f}%" for value in values],
            padding=4,
        )
    ax.axhline(0.0, color="#374151", linewidth=0.8)
    ax.set_xticks(x, [LABELS[state] for state in STATES])
    ax.set_ylabel(r"Induced-drag reduction relative to rigid baseline [%]")
    ax.set_title("Best feasible induced-drag reduction")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    save_figure(fig, output, "01_best_cdi_reduction")


def plot_design_space(
    rows: list[dict], baseline: dict[str, dict], selected: dict, output: Path
) -> None:
    fig, axes = plt.subplots(
        1, 2, figsize=(11.2, 4.8), sharey=True, constrained_layout=True
    )
    for ax, state in zip(axes, STATES):
        baseline_cdi = as_float(baseline[state], "CDi")
        for concept in CONCEPTS:
            subset = [
                row
                for row in rows
                if row["flight_state"] == state
                and row["concept"] == concept
            ]
            x = [100.0 * as_float(row, "root_bending_utilization") for row in subset]
            y = [
                100.0 * (baseline_cdi - as_float(row, "CDi")) / baseline_cdi
                for row in subset
            ]
            ax.scatter(
                x,
                y,
                s=25,
                facecolors="none",
                edgecolors=COLORS[concept],
                linewidths=0.8,
                alpha=0.75,
                label=LABELS[concept],
            )
            best = selected[(concept, state)]
            ax.scatter(
                [100.0 * as_float(best, "root_bending_utilization")],
                [
                    100.0
                    * (baseline_cdi - as_float(best, "CDi"))
                    / baseline_cdi
                ],
                marker="*",
                s=140,
                color=COLORS[concept],
                edgecolor="#111827",
                linewidth=0.6,
                zorder=5,
            )
        ax.axvline(
            100.0,
            color=COLORS["limit"],
            linestyle="--",
            linewidth=1.2,
            label="Bending limit" if state == STATES[0] else None,
        )
        ax.axhline(0.0, color="#6B7280", linewidth=0.7)
        ax.set_title(LABELS[state])
        ax.set_xlabel("Half-wing root-bending utilization [%]")
        ax.grid(color="#E5E7EB", linewidth=0.7)
    axes[0].set_ylabel(r"Induced-drag reduction from rigid baseline [%]")
    handles, labels = axes[0].get_legend_handles_labels()
    axes[1].legend(handles, labels, frameon=False, loc="lower right")
    fig.suptitle("Exact design space and active early-cruise constraint")
    save_figure(fig, output, "02_constraint_design_space")


def plot_convergence(
    seed_rows: list[dict],
    batches: dict[int, list[dict]],
    baseline: dict[str, dict],
    output: Path,
) -> None:
    fig, axes = plt.subplots(
        1, 2, figsize=(10.8, 4.8), sharey=False, constrained_layout=True
    )
    for ax, state in zip(axes, STATES):
        baseline_cdi = as_float(baseline[state], "CDi")
        for concept in CONCEPTS:
            cumulative = [
                row
                for row in seed_rows
                if row["flight_state"] == state
                and row["concept"] == concept
                and is_feasible(row)
            ]
            values = []
            for batch in [0, 1, 2]:
                if batch:
                    cumulative.extend(
                        row
                        for row in batches[batch]
                        if row["flight_state"] == state
                        and row["concept"] == concept
                        and is_feasible(row)
                    )
                best_cdi = min(as_float(row, "CDi") for row in cumulative)
                values.append(100.0 * (baseline_cdi - best_cdi) / baseline_cdi)
            ax.plot(
                [0, 1, 2],
                values,
                marker="o",
                linewidth=2.0,
                color=COLORS[concept],
                label=LABELS[concept],
            )
            for x, value in enumerate(values):
                ax.annotate(
                    f"{value:.2f}%",
                    (x, value),
                    xytext=(0, 7),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
        ax.set_title(LABELS[state])
        ax.set_xticks([0, 1, 2], ["Seed DOE", "Batch 1", "Batch 2"])
        ax.set_ylabel("Best feasible induced-drag reduction [%]")
        ax.grid(color="#E5E7EB", linewidth=0.7)
    axes[0].legend(frameon=False)
    fig.suptitle("Surrogate-assisted optimization convergence")
    save_figure(fig, output, "03_optimization_convergence")


def plot_schedules(
    project: Path, selected: dict, output: Path
) -> None:
    fig, axes = plt.subplots(
        2, 2, figsize=(10.8, 7.2), sharex=True, constrained_layout=True
    )
    for column, state in enumerate(STATES):
        for row_index, concept in enumerate(CONCEPTS):
            ax = axes[row_index, column]
            best = selected[(concept, state)]
            case_dir = find_case_dir(project, best["case_id"])
            schedule_path = case_dir / f"{best['case_id']}_section_schedule.csv"
            schedule = read_rows(schedule_path)
            command_name = (
                "command_over_c"
                if concept == "trailing_edge"
                else "incremental_twist_deg"
            )
            eta = [as_float(row, "eta") for row in schedule]
            values = [as_float(row, command_name) for row in schedule]
            ax.plot(
                eta,
                values,
                marker="o",
                markersize=3.5,
                color=COLORS[concept],
                linewidth=1.8,
            )
            ax.axvspan(0.60, 1.00, color=COLORS[concept], alpha=0.08)
            ax.axhline(0.0, color="#6B7280", linewidth=0.7)
            ax.grid(color="#E5E7EB", linewidth=0.7)
            ax.set_title(f"{LABELS[state]}: {best['case_id']}", fontsize=10)
            ax.set_ylabel(
                r"$A/c$" if concept == "trailing_edge" else r"$\Delta\theta$ [deg]"
            )
            ax.set_xlabel(r"Semi-span coordinate $\eta$")
    fig.suptitle("Best feasible spanwise morphing schedules")
    save_figure(fig, output, "04_best_spanwise_schedules")


def plot_lift_distributions(
    project: Path, selected: dict, output: Path
) -> None:
    fig, axes = plt.subplots(
        1, 2, figsize=(11.0, 4.8), sharey=False, constrained_layout=True
    )
    for ax, state in zip(axes, STATES):
        baseline_loads = read_rows(
            project / "outputs" / "rigid_baseline" / state / "spanwise_loads.csv"
        )
        ax.plot(
            [as_float(row, "eta") for row in baseline_loads],
            [as_float(row, "lift_per_span_N_per_m") for row in baseline_loads],
            color=COLORS["baseline"],
            linestyle="--",
            linewidth=1.8,
            label="Rigid baseline",
        )
        for concept in CONCEPTS:
            best = selected[(concept, state)]
            case_dir = find_case_dir(project, best["case_id"])
            loads = read_rows(
                case_dir / "evaluation" / state / "spanwise_loads.csv"
            )
            ax.plot(
                [as_float(row, "eta") for row in loads],
                [as_float(row, "lift_per_span_N_per_m") for row in loads],
                color=COLORS[concept],
                linewidth=1.8,
                label=LABELS[concept],
            )
        ax.axvspan(0.60, 1.00, color="#D1FAE5", alpha=0.35)
        ax.set_title(LABELS[state])
        ax.set_xlabel(r"Semi-span coordinate $\eta$")
        ax.set_ylabel("Lift per unit span [N/m]")
        ax.grid(color="#E5E7EB", linewidth=0.7)
    axes[0].legend(frameon=False)
    fig.suptitle("Spanwise loading of the best feasible designs")
    save_figure(fig, output, "05_best_spanwise_lift_distributions")


def plot_cross_state(
    all_rows: list[dict], selected: dict, output: Path
) -> list[dict]:
    result: list[dict] = []
    fig, ax = plt.subplots(figsize=(9.4, 5.2), constrained_layout=True)
    x = np.arange(len(CONCEPTS))
    width = 0.30
    early_values = []
    late_values = []
    adaptation_benefits = []
    for concept in CONCEPTS:
        early_id = selected[(concept, "early_cruise")]["case_id"]
        late_id = selected[(concept, "late_cruise")]["case_id"]
        early_shape_late = next(
            row
            for row in all_rows
            if row["case_id"] == early_id
            and row["flight_state"] == "late_cruise"
        )
        late_shape_late = selected[(concept, "late_cruise")]
        benefit = 100.0 * (
            as_float(early_shape_late, "CDi")
            - as_float(late_shape_late, "CDi")
        ) / as_float(early_shape_late, "CDi")
        early_values.append(as_float(early_shape_late, "CDi"))
        late_values.append(as_float(late_shape_late, "CDi"))
        adaptation_benefits.append(benefit)
        late_id_early = next(
            row
            for row in all_rows
            if row["case_id"] == late_id
            and row["flight_state"] == "early_cruise"
        )
        result.append(
            {
                "concept": concept,
                "early_optimized_case": early_id,
                "late_optimized_case": late_id,
                "early_shape_CDi_at_late_cruise": as_float(
                    early_shape_late, "CDi"
                ),
                "late_shape_CDi_at_late_cruise": as_float(
                    late_shape_late, "CDi"
                ),
                "late_cruise_adaptation_benefit_percent": benefit,
                "late_shape_root_utilization_at_early_cruise": as_float(
                    late_id_early, "root_bending_utilization"
                ),
                "late_shape_feasible_at_early_cruise": is_feasible(
                    late_id_early
                ),
            }
        )
    bars_a = ax.bar(
        x - width / 2,
        np.array(early_values) * 1.0e4,
        width,
        color="#D1D5DB",
        edgecolor="#374151",
        label="Early-optimized shape at late cruise",
    )
    bars_b = ax.bar(
        x + width / 2,
        np.array(late_values) * 1.0e4,
        width,
        color=COLORS["trailing_edge"],
        edgecolor="#374151",
        label="Late-optimized shape at late cruise",
    )
    ax.bar_label(bars_a, fmt="%.2f", padding=3, fontsize=8)
    ax.bar_label(
        bars_b,
        labels=[
            f"{value * 1.0e4:.2f}\n({benefit:.2f}% lower)"
            for value, benefit in zip(late_values, adaptation_benefits)
        ],
        padding=3,
        fontsize=8,
    )
    ax.set_xticks(x, [LABELS[concept] for concept in CONCEPTS])
    ax.set_ylabel(r"$C_{D_i}$ [drag counts, $10^{-4}$]")
    ax.set_title("Benefit of adapting the shape from early to late cruise")
    ax.legend(frameon=False)
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    save_figure(fig, output, "06_cross_state_adaptation")
    return result


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    output = project / "plot" / "cruise_comparison"
    output.mkdir(parents=True, exist_ok=True)
    baseline = {
        row["flight_state"]: row
        for row in read_rows(
            project / "outputs" / "rigid_baseline" / "rigid_baseline_summary.csv"
        )
    }
    seed_rows = read_rows(
        project / "outputs" / "seed_evaluations" / "all_seed_results.csv"
    )
    evaluation_root = project / "outputs" / "optimization_evaluations"
    batches: dict[int, list[dict]] = {}
    for path in sorted(evaluation_root.glob("batch_*_results.csv")):
        try:
            batch = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        batches[batch] = read_rows(path)
    if not batches:
        raise RuntimeError(f"No optimization batches found in {evaluation_root}")
    all_rows = seed_rows + [
        row for batch in sorted(batches) for row in batches[batch]
    ]
    selected, summary = best_rows(all_rows, baseline)
    write_csv(output / "best_design_summary.csv", summary)
    plot_reduction(summary, output)
    plot_design_space(all_rows, baseline, selected, output)
    plot_convergence(seed_rows, batches, baseline, output)
    plot_schedules(project, selected, output)
    plot_lift_distributions(project, selected, output)
    adaptation = plot_cross_state(all_rows, selected, output)
    write_csv(output / "cross_state_adaptation.csv", adaptation)
    (output / "selected_cases.json").write_text(
        json.dumps(
            {
                f"{concept}_{state}": row["case_id"]
                for (concept, state), row in selected.items()
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote summary and plots to {output}")


if __name__ == "__main__":
    main()

