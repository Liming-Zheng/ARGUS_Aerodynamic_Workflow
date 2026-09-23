from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


BASELINE_CDI = 0.009167626874
LEGACY_CASE = "mbr_c01_l011"
LEGACY_CDI = 0.008838448645
LEGACY_BENDING_INCREASE_PERCENT = 4.126495760912255


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument(
        "--case-id",
        default="mcv2_i002_c01",
        help="Audited strict candidate stored below outputs/unit_audit_2026_07_28.",
    )
    return parser.parse_args()


def read_one(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        return next(csv.DictReader(handle))


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(row: dict, name: str) -> float:
    return float(row[name])


def save(fig, output: Path, stem: str):
    for suffix in (".png", ".svg", ".pdf"):
        kwargs = {"dpi": 220} if suffix == ".png" else {}
        fig.savefig(output / f"{stem}{suffix}", bbox_inches="tight", **kwargs)
    plt.close(fig)


def main():
    args = parse_args()
    project = args.project.resolve()
    case_dir = (
        project
        / "outputs"
        / "unit_audit_2026_07_28"
        / "strict_validation"
        / args.case_id
    )
    output = project / "plot" / "unit_audit_2026_07_28"
    output.mkdir(parents=True, exist_ok=True)

    strict = read_one(case_dir / f"{args.case_id}_optimization_result.csv")
    schedule = read_rows(case_dir / f"{args.case_id}_section_schedule.csv")
    loads = read_rows(case_dir / f"{args.case_id}_spanwise_loads.csv")

    cdi = number(strict, "CDi")
    summary = {
        "audit_date": "2026-07-28",
        "baseline_CDi": BASELINE_CDI,
        "legacy_candidate": LEGACY_CASE,
        "legacy_candidate_CDi": LEGACY_CDI,
        "legacy_hinge_constraint_status": "withdrawn",
        "audited_candidate": args.case_id,
        "audited_candidate_CDi": cdi,
        "CDi_change_from_baseline": cdi - BASELINE_CDI,
        "CDi_reduction_percent": 100.0 * (BASELINE_CDI - cdi) / BASELINE_CDI,
        "root_bending_moment_Nm": number(strict, "root_bending_moment_Nm"),
        "root_bending_increase_percent": number(
            strict, "root_bending_increase_percent"
        ),
        "root_bending_limit_percent": 6.8,
        "max_adjacent_delta": number(strict, "max_adjacent_delta"),
        "max_adjacent_delta_limit": 0.018,
        "hinge_moment_status": strict["hinge_moment_status"],
        "strict_CL": number(strict, "CL"),
        "strict_CL_error": number(strict, "CL_error"),
        "strict_feasible": strict["feasible"].lower() == "true",
    }
    (output / "unit_audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "unit_audit_summary.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)

    labels = ["Rigid baseline", "Legacy mbr", "Audited mcv2"]
    cdi_values = [BASELINE_CDI, LEGACY_CDI, cdi]
    bending_values = [
        0.0,
        LEGACY_BENDING_INCREASE_PERCENT,
        summary["root_bending_increase_percent"],
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), constrained_layout=True)
    colors = ["#4C566A", "#D08770", "#2A9D8F"]
    axes[0].bar(labels, cdi_values, color=colors)
    axes[0].set_ylabel(r"$C_{D_i}$")
    axes[0].set_title("Fixed-lift induced drag")
    axes[0].tick_params(axis="x", rotation=15)
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(labels, bending_values, color=colors)
    axes[1].axhline(6.8, color="#C0392B", ls="--", label="6.8% limit")
    axes[1].set_ylabel("Root-bending increase [%]")
    axes[1].set_title("Audited feasibility criterion")
    axes[1].tick_params(axis="x", rotation=15)
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend()
    save(fig, output, "01_audited_candidate_comparison")

    eta = np.asarray([number(row, "eta") for row in schedule])
    amplitude = np.asarray([number(row, "A_local_over_c") for row in schedule])
    te_native = np.asarray([
        number(row, "TE_displacement_m") for row in schedule
    ])
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 6.3), sharex=True)
    axes[0].plot(eta, amplitude, marker="o", color="#0076A8", lw=2)
    axes[0].set_ylabel(r"$A/c$")
    axes[0].set_title(f"{args.case_id}: audited spanwise command")
    axes[1].plot(
        eta,
        1000.0 * 0.3048 * te_native,
        marker="s",
        color="#E67E22",
        lw=2,
    )
    axes[1].set_ylabel("TE displacement [mm]")
    axes[1].set_xlabel(r"$\eta=y/(b/2)$")
    for ax in axes:
        ax.axvspan(0.60, 1.00, color="#DDEFE8", alpha=0.7)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    save(fig, output, "02_audited_candidate_schedule")

    load_eta = np.asarray([number(row, "eta") for row in loads])
    series = [
        ("lift_per_span_N_per_m", "Lift per span [N/m]", "#2A9D8F"),
        ("induced_drag_per_span_N_per_m", "Induced drag per span [N/m]", "#0076A8"),
        ("sectional_cl", r"Sectional $c_l$", "#6C5CE7"),
    ]
    fig, axes = plt.subplots(3, 1, figsize=(9.5, 8.0), sharex=True)
    for ax, (field, ylabel, color) in zip(axes, series):
        ax.plot(
            load_eta,
            [number(row, field) for row in loads],
            color=color,
            lw=2,
        )
        ax.axvspan(0.60, 1.00, color="#DDEFE8", alpha=0.7)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
    axes[0].set_title(
        f"{args.case_id}: strict spanwise loads at the audited SI condition"
    )
    axes[-1].set_xlabel(r"$\eta=y/(b/2)$")
    fig.tight_layout()
    save(fig, output, "03_audited_candidate_spanwise_loads")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

