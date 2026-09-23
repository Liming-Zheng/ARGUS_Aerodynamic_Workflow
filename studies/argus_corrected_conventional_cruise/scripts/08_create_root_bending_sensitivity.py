"""Create an exact-sample sensitivity study for the root-bending allowance."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


STATES = ["early_cruise", "late_cruise"]
CONCEPTS = ["rigid", "conventional_hinged", "trailing_edge", "twist"]
LABELS = {
    "rigid": "Rigid baseline",
    "conventional_hinged": "Conventional hinged",
    "trailing_edge": "Trailing-edge camber",
    "twist": "Distributed twist",
    "early_cruise": "Early cruise",
    "late_cruise": "Late cruise",
}
COLORS = {
    "rigid": "#4B5563",
    "conventional_hinged": "#6B7280",
    "trailing_edge": "#0076A8",
    "twist": "#D97706",
}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_database(project: Path) -> tuple[list[dict], dict[str, dict]]:
    cruise = project.parent / "argus_corrected_cruise_comparison"
    baseline = {
        row["flight_state"]: row
        for row in read_rows(
            cruise / "outputs" / "rigid_baseline" / "rigid_baseline_summary.csv"
        )
    }
    rows: list[dict] = []
    for path in [
        cruise / "outputs" / "seed_evaluations" / "all_seed_results.csv",
        *sorted(
            (cruise / "outputs" / "optimization_evaluations").glob(
                "batch_*_results.csv"
            )
        ),
        *sorted((project / "outputs" / "evaluations").glob("batch_*_results.csv")),
    ]:
        rows.extend(read_rows(path))
    return rows, baseline


def best_under_limit(
    rows: list[dict], state: str, concept: str, limit_nm: float
) -> dict | None:
    candidates = [
        row
        for row in rows
        if row["flight_state"] == state
        and row["concept"] == concept
        and float(row["half_wing_root_bending_moment_Nm"]) <= limit_nm
    ]
    return min(candidates, key=lambda row: float(row["CDi"])) if candidates else None


def create_summary(
    rows: list[dict], baseline: dict[str, dict], ratios: np.ndarray
) -> list[dict]:
    nominal = float(baseline["early_cruise"]["half_wing_root_bending_moment_Nm"])
    summary: list[dict] = []
    for state in STATES:
        baseline_cdi = float(baseline[state]["CDi"])
        for ratio in ratios:
            limit = nominal * ratio
            rigid_feasible = (
                float(baseline[state]["half_wing_root_bending_moment_Nm"]) <= limit
            )
            summary.append(
                {
                    "flight_state": state,
                    "concept": "rigid",
                    "root_limit_ratio": ratio,
                    "root_limit_Nm": limit,
                    "case_id": baseline[state]["case_id"] if rigid_feasible else "",
                    "CDi": baseline_cdi if rigid_feasible else "",
                    "CDi_reduction_percent": 0.0 if rigid_feasible else "",
                    "root_bending_Nm": baseline[state]["half_wing_root_bending_moment_Nm"]
                    if rigid_feasible
                    else "",
                    "sample_available": rigid_feasible,
                }
            )
            for concept in CONCEPTS[1:]:
                best = best_under_limit(rows, state, concept, limit)
                summary.append(
                    {
                        "flight_state": state,
                        "concept": concept,
                        "root_limit_ratio": ratio,
                        "root_limit_Nm": limit,
                        "case_id": best["case_id"] if best else "",
                        "CDi": float(best["CDi"]) if best else "",
                        "CDi_reduction_percent": (
                            100.0 * (baseline_cdi - float(best["CDi"])) / baseline_cdi
                            if best
                            else ""
                        ),
                        "root_bending_Nm": (
                            float(best["half_wing_root_bending_moment_Nm"])
                            if best
                            else ""
                        ),
                        "sample_available": best is not None,
                    }
                )
    return summary


def plot(summary: list[dict], output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), sharey=False)
    for ax, state in zip(axes, STATES):
        for concept in CONCEPTS:
            selected = [
                row
                for row in summary
                if row["flight_state"] == state and row["concept"] == concept
            ]
            x = np.array([100.0 * float(row["root_limit_ratio"]) for row in selected])
            y = np.array(
                [
                    float(row["CDi_reduction_percent"])
                    if row["CDi_reduction_percent"] != ""
                    else np.nan
                    for row in selected
                ]
            )
            ax.step(
                x,
                y,
                where="post",
                color=COLORS[concept],
                linewidth=2.0,
                linestyle="--" if concept == "rigid" else "-",
                label=LABELS[concept],
            )
        ax.axvline(100.0, color="#111827", linewidth=1.0, linestyle=":")
        ax.axhline(0.0, color="#9CA3AF", linewidth=0.8)
        ax.set_title(LABELS[state])
        ax.set_xlabel("Allowed root bending / nominal early-cruise limit [%]")
        ax.grid(color="#E5E7EB", linewidth=0.7)
    axes[0].set_ylabel(r"Best exact-sample $C_{D_i}$ reduction [%]")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.91),
        ncol=4,
        frameon=False,
    )
    fig.suptitle(
        "Sensitivity of the four-concept ranking to the root-bending allowance",
        y=0.99,
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.82))
    for suffix in ["png", "svg", "pdf"]:
        fig.savefig(
            output / f"06_root_bending_limit_sensitivity.{suffix}",
            dpi=240 if suffix == "png" else None,
            bbox_inches="tight",
        )
    plt.close(fig)


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    output = project / "plot" / "four_concept_comparison"
    output.mkdir(parents=True, exist_ok=True)
    rows, baseline = load_database(project)
    ratios = np.round(np.arange(0.88, 1.081, 0.005), 3)
    summary = create_summary(rows, baseline, ratios)
    write_rows(output / "root_bending_limit_sensitivity.csv", summary)
    plot(summary, output)
    print(f"Wrote root-bending sensitivity package to {output}")


if __name__ == "__main__":
    main()

