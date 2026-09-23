"""Rank the audited cruise cases using VSPAERO wake-induced drag (CDiw).

This script consumes only the non-destructive outputs created by
``09_run_far_field_audit.py``.  It keeps the historical near-field ranking in
the comparison so that any change in selected geometry is explicit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CONCEPT_LABELS = {
    "rigid": "Rigid baseline",
    "conventional_hinged": "Conventional hinged",
    "trailing_edge": "Continuous trailing edge",
    "twist": "Distributed twist",
}
CONCEPT_COLORS = {
    "rigid": "#4b5563",
    "conventional_hinged": "#7c3aed",
    "trailing_edge": "#0086b3",
    "twist": "#d97706",
}
ADAPTIVE_CONCEPTS = ["conventional_hinged", "trailing_edge", "twist"]
STATES = ["early_cruise", "late_cruise"]


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    return parser.parse_args()


def save_figure(fig: plt.Figure, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    for suffix in [".png", ".pdf", ".svg"]:
        fig.savefig(stem.with_suffix(suffix), dpi=240, bbox_inches="tight")
    plt.close(fig)


def load_results(root: Path) -> pd.DataFrame:
    path = root / "all_results.csv"
    data = pd.read_csv(path)
    expected = 2 * len(list((root / "cases").glob("*/audit_complete.json")))
    if len(data) != expected:
        raise RuntimeError(f"Expected {expected} state results, found {len(data)}")
    numeric = [
        "CL",
        "target_CL",
        "CDi_near_field",
        "CDiw_far_field",
        "root_bending_utilization",
        "half_wing_root_bending_moment_Nm",
        "e_near_field_total_CL",
        "e_far_field_total_CL",
    ]
    data[numeric] = data[numeric].apply(pd.to_numeric)
    data["root_bending_feasible"] = (
        data["root_bending_feasible"].astype(str).str.lower() == "true"
    )
    baseline = (
        data[data.case_id == "rigid_baseline"]
        .set_index("flight_state")[["CDi_near_field", "CDiw_far_field"]]
    )
    for field in ["CDi_near_field", "CDiw_far_field"]:
        reference = data.flight_state.map(baseline[field])
        suffix = "near" if field.startswith("CDi_") else "far"
        data[f"reduction_{suffix}_percent"] = 100.0 * (reference - data[field]) / reference
        data[f"reduction_{suffix}_counts"] = 1.0e4 * (reference - data[field])
    extracted = data.case_id.str.extract(r"^ff_(?:te|tw)_b(\d+)_", expand=False)
    data["far_field_refinement_batch"] = pd.to_numeric(
        extracted, errors="coerce"
    ).fillna(0).astype(int)
    return data


def select_cases(data: pd.DataFrame) -> pd.DataFrame:
    selected: list[dict] = []
    for state in STATES:
        for concept in ADAPTIVE_CONCEPTS:
            pool = data[
                (data.flight_state == state)
                & (data.concept == concept)
                & data.root_bending_feasible
            ]
            if pool.empty:
                continue
            for method, field in [
                ("historical_near_field", "CDi_near_field"),
                ("audited_far_field", "CDiw_far_field"),
            ]:
                row = pool.loc[pool[field].idxmin()].to_dict()
                row["selection_method"] = method
                selected.append(row)
    return pd.DataFrame(selected)


def add_design_metadata(root: Path, selected: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in selected.to_dict("records"):
        design_path = root / "cases" / row["case_id"] / "source_design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        commands = design.get("control_values", design.get("segment_deflections_deg", []))
        row["design_commands"] = json.dumps(commands)
        row["design_command_units"] = design.get("command_units", "deg")
        row["proposal_reason"] = design.get("proposal_reason", design.get("seed_type", ""))
        rows.append(row)
    return pd.DataFrame(rows)


def plot_concept_comparison(selected: pd.DataFrame, plot_root: Path) -> None:
    far = selected[selected.selection_method == "audited_far_field"]
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    x = np.arange(len(ADAPTIVE_CONCEPTS))
    width = 0.34
    for offset, state in [(-width / 2, "early_cruise"), (width / 2, "late_cruise")]:
        subset = far[far.flight_state == state].set_index("concept")
        values = [subset.loc[c, "reduction_far_percent"] for c in ADAPTIVE_CONCEPTS]
        bars = ax.bar(x + offset, values, width, label=state.replace("_", " ").title())
        ax.bar_label(bars, fmt="%.2f%%", fontsize=8, padding=2)
    ax.set_xticks(x, [CONCEPT_LABELS[c] for c in ADAPTIVE_CONCEPTS])
    ax.set_ylabel(r"Far-field induced-drag reduction, $\Delta C_{D_{iw}}$ [%]")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    ax.set_title("Best feasible audited case in the existing exact design space")
    save_figure(fig, plot_root / "01_far_field_concept_comparison")


def plot_design_space(data: pd.DataFrame, selected: pd.DataFrame, plot_root: Path) -> None:
    far = selected[selected.selection_method == "audited_far_field"]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharey=True)
    for ax, state in zip(axes, STATES):
        subset = data[(data.flight_state == state) & (data.concept != "rigid")]
        for concept in ADAPTIVE_CONCEPTS:
            concept_rows = subset[subset.concept == concept]
            ax.scatter(
                100.0 * concept_rows.root_bending_utilization,
                concept_rows.reduction_far_percent,
                s=28,
                alpha=0.70,
                color=CONCEPT_COLORS[concept],
                label=CONCEPT_LABELS[concept],
            )
            chosen = far[(far.flight_state == state) & (far.concept == concept)]
            if not chosen.empty:
                ax.scatter(
                    100.0 * chosen.root_bending_utilization,
                    chosen.reduction_far_percent,
                    s=125,
                    marker="*",
                    edgecolor="black",
                    linewidth=0.7,
                    color=CONCEPT_COLORS[concept],
                    zorder=5,
                )
        ax.axvline(100.1, color="#c2410c", linestyle="--", linewidth=1.2)
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_xlabel("Root-bending limit utilization [%]")
        ax.set_title(state.replace("_", " ").title())
        ax.grid(alpha=0.22)
    axes[0].set_ylabel(r"Far-field induced-drag reduction, $\Delta C_{D_{iw}}$ [%]")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.subplots_adjust(bottom=0.20)
    fig.suptitle("Audited exact design space: benefit versus structural constraint")
    save_figure(fig, plot_root / "02_far_field_design_space")


def plot_selection_change(selected: pd.DataFrame, plot_root: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharey=True)
    for ax, state in zip(axes, STATES):
        subset = selected[selected.flight_state == state]
        x = np.arange(len(ADAPTIVE_CONCEPTS))
        width = 0.34
        for offset, method, label in [
            (-width / 2, "historical_near_field", "Geometry selected by near-field CDi"),
            (width / 2, "audited_far_field", "Geometry selected by far-field CDiw"),
        ]:
            method_rows = subset[subset.selection_method == method].set_index("concept")
            values = [method_rows.loc[c, "reduction_far_percent"] for c in ADAPTIVE_CONCEPTS]
            bars = ax.bar(x + offset, values, width, label=label)
            ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=2)
        ax.set_xticks(x, ["Hinged", "TE camber", "Twist"])
        ax.set_title(state.replace("_", " ").title())
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Actual far-field induced-drag reduction [%]")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.subplots_adjust(bottom=0.21)
    fig.suptitle("Effect of correcting the optimization objective")
    save_figure(fig, plot_root / "03_near_vs_far_selection")


def plot_spanwise_loads(root: Path, selected: pd.DataFrame, plot_root: Path) -> None:
    far = selected[selected.selection_method == "audited_far_field"]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.7), sharey=True)
    for ax, state in zip(axes, STATES):
        cases = [("rigid_baseline", "rigid")]
        cases.extend(
            (row.case_id, row.concept)
            for row in far[far.flight_state == state].itertuples()
        )
        for case_id, concept in cases:
            path = root / "cases" / case_id / state / "spanwise_loads.csv"
            loads = pd.read_csv(path)
            ax.plot(
                loads["eta"],
                loads["lift_per_span_N_per_m"],
                linewidth=2.0 if concept == "rigid" else 1.6,
                color=CONCEPT_COLORS[concept],
                label=CONCEPT_LABELS[concept],
            )
        ax.axvspan(0.60, 1.00, color="#d1fae5", alpha=0.35, linewidth=0)
        ax.set_xlabel(r"Semi-span coordinate $\eta$")
        ax.set_title(state.replace("_", " ").title())
        ax.grid(alpha=0.22)
    axes[0].set_ylabel("Lift per unit span [N/m]")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False)
    fig.subplots_adjust(bottom=0.22)
    fig.suptitle("Spanwise loading of the far-field-selected geometries")
    save_figure(fig, plot_root / "04_selected_spanwise_loads")


def plot_refinement_convergence(data: pd.DataFrame, plot_root: Path) -> None:
    max_batch = int(data.far_field_refinement_batch.max())
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), sharey=True)
    for ax, state in zip(axes, STATES):
        for concept in ["trailing_edge", "twist"]:
            values = []
            for batch in range(max_batch + 1):
                pool = data[
                    (data.flight_state == state)
                    & (data.concept == concept)
                    & data.root_bending_feasible
                    & (data.far_field_refinement_batch <= batch)
                ]
                values.append(pool.reduction_far_percent.max())
            ax.plot(
                range(max_batch + 1),
                values,
                marker="o",
                linewidth=2.0,
                color=CONCEPT_COLORS[concept],
                label=CONCEPT_LABELS[concept],
            )
            for batch, value in enumerate(values):
                ax.annotate(
                    f"{value:.2f}%",
                    (batch, value),
                    xytext=(
                        0,
                        9 if concept == "trailing_edge" else -17,
                    ),
                    textcoords="offset points",
                    ha="center",
                    va="bottom" if concept == "trailing_edge" else "top",
                    fontsize=8,
                )
        ax.set_xticks(
            range(max_batch + 1),
            ["Existing\nsamples", *[f"CDiw batch {i}" for i in range(1, max_batch + 1)]],
        )
        ax.set_title(state.replace("_", " ").title())
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Best feasible far-field induced-drag reduction [%]")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.subplots_adjust(bottom=0.24)
    fig.suptitle("Exact-validation convergence after correcting the objective to CDiw")
    save_figure(fig, plot_root / "05_far_field_refinement_convergence")


def plot_root_limit_sensitivity(
    data: pd.DataFrame, plot_root: Path, output_root: Path
) -> None:
    scales = np.linspace(0.88, 1.08, 81)
    nominal_limit = float(
        data.loc[
            (data.case_id == "rigid_baseline")
            & (data.flight_state == "early_cruise"),
            "root_bending_limit_Nm",
        ].iloc[0]
    )
    rows: list[dict] = []
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.7), sharey=True)
    for ax, state in zip(axes, STATES):
        for concept in ADAPTIVE_CONCEPTS:
            subset = data[(data.flight_state == state) & (data.concept == concept)]
            values = []
            for scale in scales:
                feasible = subset[
                    subset.half_wing_root_bending_moment_Nm
                    <= nominal_limit * scale * 1.001
                ]
                value = (
                    float(feasible.reduction_far_percent.max())
                    if not feasible.empty
                    else np.nan
                )
                values.append(value)
                rows.append(
                    {
                        "flight_state": state,
                        "concept": concept,
                        "root_limit_scale": scale,
                        "best_far_field_reduction_percent": value,
                    }
                )
            ax.plot(
                100.0 * scales,
                values,
                linewidth=2.0,
                color=CONCEPT_COLORS[concept],
                label=CONCEPT_LABELS[concept],
            )
        ax.axvline(100.0, color="#c2410c", linestyle="--", linewidth=1.2)
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_xlabel("Allowed root-bending moment [% of nominal limit]")
        ax.set_title(state.replace("_", " ").title())
        ax.grid(alpha=0.23)
    axes[0].set_ylabel("Best feasible far-field induced-drag reduction [%]")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.subplots_adjust(bottom=0.22)
    fig.suptitle("Far-field concept ranking sensitivity to the illustrative bending limit")
    save_figure(fig, plot_root / "06_far_field_root_limit_sensitivity")
    pd.DataFrame(rows).to_csv(
        output_root / "far_field_root_limit_sensitivity.csv", index=False
    )


def write_summary(root: Path, data: pd.DataFrame, selected: pd.DataFrame) -> None:
    far = selected[selected.selection_method == "audited_far_field"]
    summary = {
        "audit_metric": "VSPAERO wake-induced drag coefficient CDiw",
        "number_of_geometries": int(data.case_id.nunique()),
        "number_of_state_evaluations": int(len(data)),
        "far_field_refinement_batches": int(
            data.far_field_refinement_batch.max()
        ),
        "selected_cases": far[
            [
                "flight_state",
                "concept",
                "case_id",
                "CDiw_far_field",
                "reduction_far_percent",
                "reduction_far_counts",
                "root_bending_utilization",
            ]
        ].to_dict("records"),
    }
    (root / "audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Far-field induced-drag audit",
        "",
        f"- Exact geometries re-evaluated: **{summary['number_of_geometries']}**",
        f"- State evaluations: **{summary['number_of_state_evaluations']}**",
        "- Ranking metric: VSPAERO wake-induced drag coefficient `CDiw`.",
        "- The historical surface-integration `CDi` ranking is retained only for traceability.",
        "",
        "## Best feasible cases in the audited existing design space",
        "",
        "| Flight state | Concept | Case | CDiw | Reduction | Root-bending utilization |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in far.sort_values(["flight_state", "concept"]).itertuples():
        lines.append(
            f"| {row.flight_state} | {CONCEPT_LABELS[row.concept]} | `{row.case_id}` | "
            f"{row.CDiw_far_field:.9f} | {row.reduction_far_percent:.3f}% | "
            f"{100.0 * row.root_bending_utilization:.2f}% |"
        )
    lines.extend(
        [
            "",
            "",
            f"The table includes **{summary['far_field_refinement_batches']}** surrogate-assisted refinement batches proposed and exactly validated using `CDiw` as the objective.",
        ]
    )
    (root / "AUDIT_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = args.project.resolve() / "outputs" / "far_field_audit"
    plot_root = root / "plots"
    data = load_results(root)
    selected = add_design_metadata(root, select_cases(data))
    data.to_csv(root / "far_field_ranked_results.csv", index=False)
    selected.to_csv(root / "selected_cases_near_vs_far.csv", index=False)
    plot_concept_comparison(selected, plot_root)
    plot_design_space(data, selected, plot_root)
    plot_selection_change(selected, plot_root)
    plot_spanwise_loads(root, selected, plot_root)
    plot_refinement_convergence(data, plot_root)
    plot_root_limit_sensitivity(data, plot_root, root)
    write_summary(root, data, selected)
    print(f"Analyzed {data.case_id.nunique()} geometries and {len(data)} state evaluations")


if __name__ == "__main__":
    main()

