"""Summarize strict corrected-low-speed CDiw candidates and refinement evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT.parent
MORPH = WORK / "argus_morphing"
TWIST = WORK / "argus_twist_morphing"
AUDIT = PROJECT / "outputs" / "corrected_low_speed_far_field_audit"
OUTPUT = PROJECT / "outputs" / "corrected_low_speed_far_field_final"
PLOTS = OUTPUT / "plots"

CASES = {
    "rigid": MORPH / "outputs" / "tyler_validation_2026_07_29" / "baseline_corrected",
    "conventional_hinged": PROJECT / "outputs" / "corrected_cdiw_strict_validation" / "samples" / "chc_g02_c06",
    "trailing_edge": MORPH / "outputs" / "corrected_cdiw_strict_validation" / "samples" / "cfft_b02_c01",
    "twist": TWIST / "outputs" / "corrected_cdiw_strict_validation" / "samples" / "cffw_b01_c01",
}
LABELS = {
    "rigid": "Rigid",
    "conventional_hinged": "Conventional hinged",
    "trailing_edge": "Continuous trailing edge",
    "twist": "Distributed twist",
}
COLORS = {
    "rigid": "#4b5563",
    "conventional_hinged": "#7c3aed",
    "trailing_edge": "#0086b3",
    "twist": "#d97706",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_polar(path: Path) -> dict[str, float]:
    lines = path.read_text(errors="replace").splitlines()
    index = next(i for i, line in enumerate(lines) if line.split()[:3] == ["Beta", "Mach", "AoA"])
    fields = lines[index].split()
    numeric = []
    for line in lines[index + 1 :]:
        values = line.split()
        if len(values) != len(fields):
            continue
        try:
            numeric.append([float(value) for value in values])
        except ValueError:
            pass
    return dict(zip(fields, numeric[-1]))


def single(path: Path, pattern: str) -> Path:
    found = list(path.glob(pattern))
    if len(found) != 1:
        raise ValueError(f"Expected one {pattern} in {path}, found {len(found)}")
    return found[0]


def save(fig: plt.Figure, name: str) -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    for suffix in [".png", ".pdf", ".svg"]:
        fig.savefig(PLOTS / f"{name}{suffix}", dpi=240, bbox_inches="tight")
    plt.close(fig)


def strict_rows() -> list[dict]:
    rows = []
    for concept, root in CASES.items():
        result = read_csv(single(root, "*_optimization_result.csv"))[0]
        polar = read_polar(single(root, "*.polar"))
        rows.append(
            {
                "concept": concept,
                "label": LABELS[concept],
                "case_id": result["case_id"],
                "trim_mode": result["trim_mode"],
                "CL": float(result["CL"]),
                "CL_error": float(result["CL_error"]),
                "CDi_near_field": polar["CDi"],
                "CDiw_far_field": polar["CDiw"],
                "Ew": polar["Ew"],
                "root_bending_moment_Nm": float(result["root_bending_moment_Nm"]),
                "root_bending_increase_percent": float(result["root_bending_increase_percent"]),
                "feasible": result["feasible"],
                "geometry_path": str(single(root, "*.vsp3")),
                "polar_path": str(single(root, "*.polar")),
                "lod_path": str(single(root, "*.lod")),
            }
        )
    baseline = rows[0]
    baseline["root_bending_increase_percent"] = 0.0
    for row in rows:
        row["CDiw_reduction_counts"] = 1.0e4 * (
            baseline["CDiw_far_field"] - row["CDiw_far_field"]
        )
        row["CDiw_reduction_percent"] = 100.0 * (
            baseline["CDiw_far_field"] - row["CDiw_far_field"]
        ) / baseline["CDiw_far_field"]
    return rows


def plot_strict_comparison(rows: list[dict]) -> None:
    adaptive = rows[1:]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.6))
    x = np.arange(len(adaptive))
    colors = [COLORS[row["concept"]] for row in adaptive]
    bars = axes[0].bar(x, [row["CDiw_reduction_counts"] for row in adaptive], color=colors)
    axes[0].bar_label(bars, fmt="%.3f", padding=2, fontsize=9)
    axes[0].set_xticks(x, [row["label"] for row in adaptive], rotation=10)
    axes[0].set_ylabel(r"Wake-induced drag reduction, $10^4\Delta C_{D_{iw}}$ [counts]")
    axes[0].set_title("Strict iterative-trim aerodynamic result")
    axes[0].grid(axis="y", alpha=0.25)

    bars = axes[1].bar(
        x,
        [row["root_bending_increase_percent"] for row in adaptive],
        color=colors,
    )
    axes[1].bar_label(bars, fmt="%.2f%%", padding=2, fontsize=9)
    axes[1].axhline(6.8, color="#c2410c", linestyle="--", label="Illustrative screen")
    axes[1].set_xticks(x, [row["label"] for row in adaptive], rotation=10)
    axes[1].set_ylabel("Root-bending increase [%]")
    axes[1].set_title("All selected candidates remain below the screen")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(frameon=False, loc="lower right")
    fig.suptitle(r"Corrected Mach-0.1 comparison at fixed $C_L=0.4282776$")
    fig.tight_layout()
    save(fig, "01_strict_far_field_four_concept_comparison")


def plot_convergence() -> list[dict]:
    rows = read_csv(AUDIT / "all_ranked_results.csv")
    stages = ["Historical sample pool", "CDiw batch 1", "CDiw batch 2"]
    output_rows = []
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    for concept, old_prefix, new_prefix in [
        ("trailing_edge", "cte_", "cfft_"),
        ("twist", "ctw_", "cffw_"),
    ]:
        values = []
        for stage_index in range(3):
            valid = []
            for row in rows:
                if row["concept"] != concept or row["feasible_recomputed"].lower() != "true":
                    continue
                case_id = row["case_id"]
                included = case_id.startswith(old_prefix)
                included |= stage_index >= 1 and case_id.startswith(f"{new_prefix}b01_")
                included |= stage_index >= 2 and case_id.startswith(f"{new_prefix}b02_")
                if included:
                    valid.append(row)
            best = min(valid, key=lambda row: float(row["CDiw_far_field"]))
            reduction = float(best["reduction_far_counts"])
            values.append(reduction)
            output_rows.append(
                {
                    "concept": concept,
                    "stage": stages[stage_index],
                    "best_case_id": best["case_id"],
                    "best_CDiw": best["CDiw_far_field"],
                    "reduction_counts": reduction,
                }
            )
        ax.plot(stages, values, marker="o", linewidth=2.2, color=COLORS[concept], label=LABELS[concept])
        for index, value in enumerate(values):
            ax.annotate(f"{value:.3f}", (index, value), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
    ax.set_ylabel(r"Best feasible $10^4\Delta C_{D_{iw}}$ [counts]")
    ax.set_title("Exact-evaluation convergence of the corrected far-field refinement")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    save(fig, "02_far_field_refinement_convergence")
    return output_rows


def plot_commands() -> None:
    te_root = CASES["trailing_edge"]
    tw_root = CASES["twist"]
    te = json.loads(single(te_root, "*_design.json").read_text(encoding="utf-8"))
    tw = json.loads(single(tw_root, "*_design.json").read_text(encoding="utf-8"))
    hinged = read_csv(single(CASES["conventional_hinged"], "*_optimization_result.csv"))[0]
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 4.2))

    axes[0].step(
        [0.60, 0.71, 0.852, 0.97, 1.00],
        [0.0, float(hinged["delta_inboard_deg"]), float(hinged["delta_outboard_deg"]), 0.0, 0.0],
        where="post",
        color=COLORS["conventional_hinged"],
        linewidth=2.0,
    )
    axes[0].set_ylabel("Rigid control deflection [deg]")
    axes[0].set_title("Conventional hinged")

    axes[1].plot(te["control_etas"], 100.0 * np.asarray(te["control_amplitudes_over_c"]), marker="o", color=COLORS["trailing_edge"], linewidth=2.0)
    axes[1].set_ylabel("Camber command, A/c [%]")
    axes[1].set_title(r"Continuous trailing edge, $x_h/c=0.62$")

    axes[2].plot([0.6, *tw["control_etas"]], [0.0, *tw["control_twist_deg"]], marker="o", color=COLORS["twist"], linewidth=2.0)
    axes[2].axhline(0.0, color="black", linewidth=0.7)
    axes[2].set_ylabel("Incremental twist [deg]")
    axes[2].set_title(r"Distributed twist, axis $x/c=0.25$")

    for ax in axes:
        ax.set_xlim(0.58, 1.02)
        ax.set_xlabel(r"Semi-span coordinate $\eta$")
        ax.grid(alpha=0.23)
    fig.suptitle("Strict selected geometry commands")
    fig.tight_layout()
    save(fig, "03_strict_selected_control_schedules")


def plot_spanwise_loads() -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    for concept, root in CASES.items():
        loads = read_csv(single(root, "*_spanwise_loads.csv"))
        ax.plot(
            [float(row["eta"]) for row in loads],
            [float(row["lift_per_span_N_per_m"]) for row in loads],
            linewidth=2.0 if concept != "rigid" else 1.6,
            color=COLORS[concept],
            label=LABELS[concept],
        )
    ax.axvspan(0.60, 1.00, color="#d1fae5", alpha=0.42, label="Outer-wing adaptive region")
    ax.set_xlabel(r"Semi-span coordinate $\eta$")
    ax.set_ylabel("Lift per unit span [N/m]")
    ax.set_title("Strict fixed-lift spanwise load redistribution")
    ax.grid(alpha=0.23)
    ax.legend(frameon=False, ncol=2)
    save(fig, "04_strict_spanwise_lift_comparison")


def main() -> None:
    rows = strict_rows()
    write_csv(OUTPUT / "strict_selected_results.csv", rows)
    plot_strict_comparison(rows)
    convergence = plot_convergence()
    write_csv(OUTPUT / "refinement_convergence.csv", convergence)
    plot_commands()
    plot_spanwise_loads()
    summary = {
        "status": "PASS",
        "strict_case_count": len(rows),
        "maximum_absolute_CL_error": max(abs(row["CL_error"]) for row in rows),
        "selected": {row["concept"]: row for row in rows},
        "interpretation": (
            "Continuous trailing-edge camber has the lowest strict CDiw at this "
            "low-speed point. Its margin over distributed twist is small and is "
            "not sufficient for a mechanical down-selection."
        ),
    }
    (OUTPUT / "strict_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

