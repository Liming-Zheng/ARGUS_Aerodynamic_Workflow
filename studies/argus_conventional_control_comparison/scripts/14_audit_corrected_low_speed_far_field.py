"""Audit the corrected four-concept low-speed study using VSPAERO CDiw.

The historical study selected designs with the near-field surface-integration
quantity CDi.  VSPAERO's wake/Trefftz-plane induced drag is CDiw.  This script
does not rerun or overwrite any aerodynamic case: it reads every native .polar
file, applies the original illustrative 6.8% root-bending screen, and reports
both historical and corrected selections.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT.parent
MORPH = WORK / "argus_morphing"
TWIST = WORK / "argus_twist_morphing"

BASELINE_DIR = (
    MORPH / "outputs" / "tyler_validation_2026_07_29" / "baseline_corrected"
)
TE_ROOT = MORPH / "outputs" / "corrected_te_optimization" / "samples"
TWIST_ROOT = TWIST / "outputs" / "corrected_twist_optimization" / "samples"
HINGED_ROOT = PROJECT / "outputs" / "corrected_low_speed" / "samples"
OUTPUT = PROJECT / "outputs" / "corrected_low_speed_far_field_audit"

CONCEPTS = ["rigid", "conventional_hinged", "trailing_edge", "twist"]
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
ROOT_BENDING_LIMIT_PERCENT = 6.8
ASPECT_RATIO = 12.0


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
    header_index = next(
        index
        for index, line in enumerate(lines)
        if line.split()[:3] == ["Beta", "Mach", "AoA"]
    )
    fields = lines[header_index].split()
    numeric_rows: list[list[float]] = []
    for line in lines[header_index + 1 :]:
        values = line.split()
        if len(values) != len(fields):
            continue
        try:
            numeric_rows.append([float(value) for value in values])
        except ValueError:
            continue
    if not numeric_rows:
        raise ValueError(f"No numeric result row found in {path}")
    return dict(zip(fields, numeric_rows[-1]))


def bool_value(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def load_case(case_dir: Path, concept: str) -> dict:
    result_files = list(case_dir.glob("*_optimization_result.csv"))
    polar_files = list(case_dir.glob("*.polar"))
    if len(result_files) != 1 or len(polar_files) != 1:
        raise ValueError(
            f"Expected one result CSV and one polar in {case_dir}; "
            f"found {len(result_files)} and {len(polar_files)}"
        )
    source = read_csv(result_files[0])[0]
    polar = read_polar(polar_files[0])
    cdi_near = float(source["CDi"])
    cdiw = polar["CDiw"]
    cl = float(source["CL"])
    bending_change = float(source["root_bending_increase_percent"])
    feasible_recorded = bool_value(source["feasible"])
    feasible_recomputed = bending_change <= ROOT_BENDING_LIMIT_PERCENT + 1.0e-12
    return {
        "concept": concept,
        "case_id": source["case_id"],
        "CL_summary": cl,
        "CL_polar": polar["CLtot"],
        "CDi_near_field": cdi_near,
        "CDi_polar": polar["CDi"],
        "CDiw_far_field": cdiw,
        "e_near_field_total_CL": cl**2 / (math.pi * ASPECT_RATIO * cdi_near),
        "e_far_field_total_CL": cl**2 / (math.pi * ASPECT_RATIO * cdiw),
        "E_polar": polar["E"],
        "Ew_polar": polar["Ew"],
        "root_bending_moment_Nm": float(source["root_bending_moment_Nm"]),
        "root_bending_increase_percent": bending_change,
        "root_bending_limit_percent": ROOT_BENDING_LIMIT_PERCENT,
        "root_bending_utilization_percent": 100.0 * bending_change / ROOT_BENDING_LIMIT_PERCENT,
        "feasible_recorded": feasible_recorded,
        "feasible_recomputed": feasible_recomputed,
        "result_csv": str(result_files[0]),
        "polar_path": str(polar_files[0]),
    }


def save_all(fig: plt.Figure, stem: Path) -> None:
    for suffix in [".png", ".pdf", ".svg"]:
        fig.savefig(stem.with_suffix(suffix), dpi=240, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    rows = [load_case(BASELINE_DIR, "rigid")]
    for root, concept in [
        (HINGED_ROOT, "conventional_hinged"),
        (TE_ROOT, "trailing_edge"),
        (TWIST_ROOT, "twist"),
    ]:
        rows.extend(load_case(path, concept) for path in sorted(root.iterdir()) if path.is_dir())

    baseline = rows[0]
    for row in rows:
        for metric, label in [
            ("CDi_near_field", "near"),
            ("CDiw_far_field", "far"),
        ]:
            row[f"reduction_{label}_percent"] = 100.0 * (
                baseline[metric] - row[metric]
            ) / baseline[metric]
            row[f"reduction_{label}_counts"] = 1.0e4 * (
                baseline[metric] - row[metric]
            )

    selections: list[dict] = []
    for concept in CONCEPTS[1:]:
        feasible = [
            row for row in rows
            if row["concept"] == concept and row["feasible_recomputed"]
        ]
        for method, metric in [
            ("historical_near_field", "CDi_near_field"),
            ("audited_far_field", "CDiw_far_field"),
        ]:
            selections.append({**min(feasible, key=lambda row: row[metric]), "selection_method": method})

    plots = OUTPUT / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "all_ranked_results.csv", rows)
    write_csv(OUTPUT / "selected_cases_near_vs_far.csv", selections)

    selected_by_method = {
        method: {
            row["concept"]: row
            for row in selections
            if row["selection_method"] == method
        }
        for method in ["historical_near_field", "audited_far_field"]
    }

    fig, ax = plt.subplots(figsize=(9.4, 4.9))
    x = np.arange(3)
    width = 0.34
    for offset, method, label in [
        (-width / 2, "historical_near_field", r"Selected by near-field $C_{D_i}$"),
        (width / 2, "audited_far_field", r"Selected by wake $C_{D_{iw}}$"),
    ]:
        values = [
            selected_by_method[method][concept]["reduction_far_counts"]
            for concept in CONCEPTS[1:]
        ]
        bars = ax.bar(x + offset, values, width, label=label)
        ax.bar_label(bars, fmt="%.3f", fontsize=8, padding=2)
    ax.set_xticks(x, [LABELS[concept] for concept in CONCEPTS[1:]])
    ax.set_ylabel(r"Actual wake-induced drag reduction, $10^4\Delta C_{D_{iw}}$ [counts]")
    ax.set_title(r"Corrected Mach-0.1 study: consequence of using the proper induced-drag metric")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    save_all(fig, plots / "01_corrected_low_speed_near_vs_far_selection")

    fig, ax = plt.subplots(figsize=(8.3, 5.4))
    for concept in CONCEPTS[1:]:
        subset = [row for row in rows if row["concept"] == concept]
        ax.scatter(
            [row["root_bending_increase_percent"] for row in subset],
            [row["reduction_far_counts"] for row in subset],
            s=28,
            alpha=0.65,
            color=COLORS[concept],
            label=LABELS[concept],
        )
        best = selected_by_method["audited_far_field"][concept]
        ax.scatter(
            best["root_bending_increase_percent"],
            best["reduction_far_counts"],
            marker="*",
            s=170,
            edgecolor="black",
            linewidth=0.7,
            color=COLORS[concept],
            zorder=5,
        )
    ax.axvline(ROOT_BENDING_LIMIT_PERCENT, color="#c2410c", linestyle="--", linewidth=1.2)
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel("Root-bending increase relative to corrected rigid wing [%]")
    ax.set_ylabel(r"Wake-induced drag reduction, $10^4\Delta C_{D_{iw}}$ [counts]")
    ax.set_title(r"Corrected Mach-0.1 exact design space at fixed $C_L=0.42828$")
    ax.grid(alpha=0.23)
    ax.legend(frameon=False)
    save_all(fig, plots / "02_corrected_low_speed_far_field_design_space")

    fig, ax = plt.subplots(figsize=(6.9, 5.6))
    for concept in CONCEPTS:
        subset = [row for row in rows if row["concept"] == concept]
        ax.scatter(
            [row["CDi_near_field"] for row in subset],
            [row["CDiw_far_field"] for row in subset],
            s=25,
            alpha=0.65,
            color=COLORS[concept],
            label=LABELS[concept],
        )
    limits = [
        min(min(row["CDi_near_field"], row["CDiw_far_field"]) for row in rows),
        max(max(row["CDi_near_field"], row["CDiw_far_field"]) for row in rows),
    ]
    ax.plot(limits, limits, color="black", linestyle="--", linewidth=0.9, label="Equal metrics")
    ax.set_xlabel(r"Near-field surface-integration $C_{D_i}$")
    ax.set_ylabel(r"Wake/Trefftz-plane $C_{D_{iw}}$")
    ax.set_title("Near- and far-field induced drag are not interchangeable")
    ax.grid(alpha=0.23)
    ax.legend(frameon=False, fontsize=8)
    save_all(fig, plots / "03_corrected_low_speed_metric_crosscheck")

    cl_errors = [abs(row["CL_summary"] - row["CL_polar"]) for row in rows]
    cdi_errors = [abs(row["CDi_near_field"] - row["CDi_polar"]) for row in rows]
    feasibility_mismatches = [
        row["case_id"] for row in rows if row["feasible_recorded"] != row["feasible_recomputed"]
    ]
    far = selected_by_method["audited_far_field"]
    summary = {
        "status": "PASS" if not feasibility_mismatches else "FAIL",
        "case_count": len(rows),
        "counts_by_concept": {
            concept: sum(row["concept"] == concept for row in rows)
            for concept in CONCEPTS
        },
        "operating_point": {
            "Mach": 0.1,
            "CL_target": 0.428277635108,
            "root_bending_increase_limit_percent": ROOT_BENDING_LIMIT_PERCENT,
            "limit_status": "illustrative study screen, not a structural allowable",
        },
        "maximum_native_consistency_errors": {
            "CL": max(cl_errors),
            "CDi": max(cdi_errors),
        },
        "feasibility_mismatches": feasibility_mismatches,
        "baseline": {
            "case_id": baseline["case_id"],
            "CDi_near_field": baseline["CDi_near_field"],
            "CDiw_far_field": baseline["CDiw_far_field"],
        },
        "selected_far_field": {
            concept: {
                "case_id": far[concept]["case_id"],
                "CDiw": far[concept]["CDiw_far_field"],
                "reduction_counts": far[concept]["reduction_far_counts"],
                "reduction_percent": far[concept]["reduction_far_percent"],
                "root_bending_increase_percent": far[concept]["root_bending_increase_percent"],
            }
            for concept in CONCEPTS[1:]
        },
    }
    (OUTPUT / "audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Corrected Mach-0.1 four-concept far-field audit",
        "",
        f"All **{len(rows)}** geometries were re-ranked from their native `.polar` files.",
        "The corrected objective is wake/Trefftz-plane `CDiw`; near-field `CDi` is retained only for traceability.",
        f"The original **{ROOT_BENDING_LIMIT_PERCENT:.1f}% illustrative root-bending screen** is unchanged.",
        "",
        "| Concept | Far-field-selected case | CDiw reduction | Drag-count reduction | Root-bending increase |",
        "|---|---|---:|---:|---:|",
    ]
    for concept in CONCEPTS[1:]:
        row = far[concept]
        lines.append(
            f"| {LABELS[concept]} | `{row['case_id']}` | "
            f"{row['reduction_far_percent']:.3f}% | {row['reduction_far_counts']:.3f} | "
            f"{row['root_bending_increase_percent']:.3f}% |"
        )
    (OUTPUT / "AUDIT_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

