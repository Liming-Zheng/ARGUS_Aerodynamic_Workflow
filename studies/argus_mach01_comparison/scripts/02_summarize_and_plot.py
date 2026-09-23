"""Select the Mach 0.1 concepts and create decision-level plots."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
COLORS = {
    "rigid": "#27374D",
    "conventional_hinged": "#767676",
    "trailing_edge": "#009FC2",
    "twist": "#E37222",
}
LABELS = {
    "rigid": "Rigid",
    "conventional_hinged": "Conventional hinged",
    "trailing_edge": "Continuous trailing edge",
    "twist": "Distributed twist",
}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def numeric(row: dict, key: str) -> float:
    return float(row[key])


def save_all(fig: plt.Figure, stem: Path) -> None:
    for suffix in [".png", ".pdf", ".svg"]:
        fig.savefig(stem.with_suffix(suffix), dpi=220, bbox_inches="tight")


def main() -> None:
    config = json.loads(
        (PROJECT / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    rows = read_csv(PROJECT / "outputs" / "evaluations" / "all_results.csv")
    rigid = next(row for row in rows if row["concept"] == "rigid")
    root_limit = numeric(rigid, "half_wing_root_bending_moment_Nm")
    tolerance = float(
        config["aerodynamic_analysis"]["constraint_relative_tolerance"]
    )
    for row in rows:
        root = numeric(row, "half_wing_root_bending_moment_Nm")
        row["root_bending_limit_Nm"] = root_limit
        row["root_bending_utilization"] = root / root_limit
        row["feasible"] = str(root <= root_limit * (1.0 + tolerance))

    selected = {"rigid": rigid}
    for concept in ["conventional_hinged", "trailing_edge", "twist"]:
        feasible = [
            row for row in rows
            if row["concept"] == concept and row["feasible"] == "True"
        ]
        selected[concept] = min(feasible, key=lambda row: numeric(row, "CDi"))

    baseline_cdi = numeric(rigid, "CDi")
    summary: list[dict] = []
    for concept, row in selected.items():
        cdi = numeric(row, "CDi")
        summary.append({
            "concept": concept,
            "case_id": row["case_id"],
            "Mach": row["mach"],
            "target_CL": row["target_CL"],
            "CL": row["CL"],
            "CDi": row["CDi"],
            "CDi_reduction_percent": 100.0 * (baseline_cdi - cdi) / baseline_cdi,
            "root_bending_moment_Nm": row["half_wing_root_bending_moment_Nm"],
            "root_bending_utilization": row["root_bending_utilization"],
            "alpha_trim_deg": row["alpha_trim_deg"],
            "control_values_json": row["control_values_json"],
            "command_units": row["command_units"],
            "model_path": row["model_path"],
        })

    out = PROJECT / "plot" / "mach01_comparison"
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "mach01_selected_summary.csv", summary)
    (out / "selected_cases.json").write_text(
        json.dumps(
            {row["concept"]: row["case_id"] for row in summary},
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    geometry_dir = out / "final_geometries"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    geometry_manifest: list[dict] = []
    for concept, row in selected.items():
        source = Path(row["model_path"])
        destination = geometry_dir / f"mach01_best_{concept}_{row['case_id']}.vsp3"
        shutil.copy2(source, destination)
        geometry_manifest.append({
            "concept": concept,
            "case_id": row["case_id"],
            "source_geometry": str(source),
            "export_geometry": str(destination),
            "native_length_unit": "ft",
            "analysis_mach": 0.1,
            "target_CL": float(row["target_CL"]),
        })
    (geometry_dir / "geometry_manifest.json").write_text(
        json.dumps(geometry_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    concepts = list(selected)
    x = np.arange(len(concepts))
    reductions = [
        100.0 * (baseline_cdi - numeric(selected[c], "CDi")) / baseline_cdi
        for c in concepts
    ]
    root_changes = [
        100.0
        * (
            numeric(selected[c], "half_wing_root_bending_moment_Nm")
            / root_limit
            - 1.0
        )
        for c in concepts
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.2))
    benefit_bars = axes[0].bar(
        x, reductions, color=[COLORS[c] for c in concepts]
    )
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set_ylabel(r"$C_{D_i}$ reduction from rigid [%]")
    axes[0].set_title("Aerodynamic benefit at fixed lift coefficient")
    axes[0].bar_label(benefit_bars, fmt="%.3f", padding=3, fontsize=8)
    root_bars = axes[1].bar(
        x, root_changes, color=[COLORS[c] for c in concepts]
    )
    axes[1].axhline(0.0, color="#C44E52", linestyle="--", label="Rigid limit")
    axes[1].set_ylabel("Root-bending change from rigid [%]")
    axes[1].set_title("Load redistribution at the constraint")
    axes[1].set_ylim(min(root_changes) * 1.18, 0.006)
    for bar, value in zip(root_bars, root_changes):
        if abs(value) < 1.0e-9:
            continue
        axes[1].text(
            bar.get_x() + bar.get_width() / 2.0,
            value + 0.002,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    for axis in axes:
        axis.set_xticks(x, [LABELS[c] for c in concepts], rotation=17, ha="right")
        axis.grid(axis="y", alpha=0.25)
    fig.suptitle(r"ARGUS four-concept comparison at $M=0.1$, fixed $C_L=0.529297$")
    fig.tight_layout()
    save_all(fig, out / "01_mach01_four_concept_performance")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(7.3, 5.0))
    for concept in concepts:
        row = selected[concept]
        loads = read_csv(
            PROJECT / "outputs" / "cases" / concept / row["case_id"]
            / "spanwise_loads.csv"
        )
        eta = np.array([numeric(item, "eta") for item in loads])
        lift = np.array([numeric(item, "lift_per_span_N_per_m") for item in loads])
        norm = np.trapezoid(lift, eta)
        axis.plot(
            eta,
            lift / norm,
            linewidth=2.0,
            color=COLORS[concept],
            label=LABELS[concept],
        )
    axis.set_xlabel(r"Semi-span coordinate $\eta$")
    axis.set_ylabel("Normalized lift-distribution shape [-]")
    axis.set_title(r"Selected spanwise loading at $M=0.1$")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False)
    fig.tight_layout()
    save_all(fig, out / "02_mach01_spanwise_lift")
    plt.close(fig)

    metadata = {
        "interpretation": config["definition"],
        "selection_rule": (
            "Minimum exact VSPAERO CDi among saved geometries satisfying "
            "Mroot <= Mach-0.1 rigid Mroot with 0.1% numerical tolerance"
        ),
        "root_bending_limit_Nm": root_limit,
        "number_of_exact_cases": len(rows),
        "selected": {row["concept"]: row for row in summary},
    }
    (out / "mach01_summary.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    dictionary = [
        {
            "quantity": "CL, CD, CDi, Cm",
            "unit": "-",
            "frame_or_reference": "NASA VSPAERO reference convention",
            "condition": "Mach 0.1; each geometry independently trimmed",
            "description": "Dimensionless whole-wing aerodynamic coefficients",
        },
        {
            "quantity": "alpha_trim_deg",
            "unit": "deg",
            "frame_or_reference": "OpenVSP body axes",
            "condition": "Fixed CL = 0.529297087",
            "description": "Trimmed geometric angle of attack",
        },
        {
            "quantity": "lift_per_span_N_per_m",
            "unit": "N/m",
            "frame_or_reference": "Positive aerodynamic lift; half-wing strips",
            "condition": "ISA sea level, Mach 0.1, aircraft-scaled geometry",
            "description": "Sectional lift per unit aircraft-scale span",
        },
        {
            "quantity": "half_wing_lift_N",
            "unit": "N",
            "frame_or_reference": "One semi-span",
            "condition": "ISA sea level, Mach 0.1, fixed CL",
            "description": "Numerical strip integration of half-wing lift",
        },
        {
            "quantity": "half_wing_root_bending_moment_Nm",
            "unit": "N m",
            "frame_or_reference": "Half-wing root; positive lift times span arm",
            "condition": "ISA sea level, Mach 0.1, fixed CL",
            "description": "Aerodynamic root-bending moment without wing weight or fuel relief",
        },
        {
            "quantity": "root_bending_utilization",
            "unit": "-",
            "frame_or_reference": "Mach 0.1 rigid baseline equals 1.0",
            "condition": "Strict final selection requires utilization <= 1.0",
            "description": "Candidate root moment divided by rigid root moment",
        },
    ]
    write_csv(out / "DATA_DICTIONARY.csv", dictionary)
    print(f"Wrote {len(summary)} selected concepts and plots to {out}")


if __name__ == "__main__":
    main()

