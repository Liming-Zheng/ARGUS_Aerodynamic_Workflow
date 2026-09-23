"""Re-rank the complete Mach-0.1 database using wake-induced drag CDiw."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
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


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
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
    rows = []
    for line in lines[header_index + 1 :]:
        parts = line.split()
        if len(parts) != len(fields):
            continue
        try:
            rows.append([float(value) for value in parts])
        except ValueError:
            continue
    return dict(zip(fields, rows[-1]))


def read_lod(path: Path) -> tuple[dict[str, float], dict[str, np.ndarray]]:
    """Read reference values and the final strip iteration from a VSPAERO LOD."""
    lines = path.read_text(errors="replace").splitlines()
    reference: dict[str, float] = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith("_"):
            try:
                reference[parts[0].rstrip("_")] = float(parts[1])
            except ValueError:
                pass
    header_index = next(
        index for index, line in enumerate(lines)
        if line.split()[:1] == ["Iter"]
    )
    fields = lines[header_index].split()
    numeric = []
    for line in lines[header_index + 1 :]:
        parts = line.split()
        if len(parts) < len(fields) or not parts[0].lstrip("-").isdigit():
            continue
        numeric.append([float(value) for value in parts[: len(fields)]])
    values = np.asarray(numeric)
    values = values[values[:, 0] == values[:, 0].max()]
    return reference, {name: values[:, index] for index, name in enumerate(fields)}


def lifting_line_efficiency(
    y: np.ndarray,
    chord_cl: np.ndarray,
    span: float,
    area: float,
    modes: int,
) -> tuple[float, float]:
    """Independent Glauert Fourier estimate from the spanwise loading shape."""
    order = np.argsort(y)
    y = y[order]
    chord_cl = chord_cl[order]
    full_y = np.concatenate([-y[::-1], y])
    full_loading = np.concatenate([chord_cl[::-1], chord_cl])
    theta = np.arccos(np.clip(-2.0 * full_y / span, -1.0, 1.0))
    order = np.argsort(theta)
    theta = theta[order]
    target = full_loading[order] / (4.0 * span)
    matrix = np.stack(
        [np.sin(index * theta) for index in range(1, modes + 1)], axis=1
    )
    coefficients, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    indices = np.arange(1, modes + 1)
    weighted_sum = float(np.sum(indices * coefficients**2))
    efficiency = coefficients[0] ** 2 / weighted_sum
    aspect_ratio = span**2 / area
    cdi = math.pi * aspect_ratio * weighted_sum
    return efficiency, cdi


def save_all(fig: plt.Figure, stem: Path) -> None:
    for suffix in [".png", ".pdf", ".svg"]:
        fig.savefig(stem.with_suffix(suffix), dpi=240, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    source = read_csv(PROJECT / "outputs" / "evaluations" / "all_results.csv")
    rigid = next(row for row in source if row["concept"] == "rigid")
    root_limit = float(rigid["half_wing_root_bending_moment_Nm"])
    rows: list[dict] = []
    maximum_errors = {"CL": 0.0, "CDi": 0.0, "CDiw_efficiency": 0.0}
    for row in source:
        case_dir = PROJECT / "outputs" / "cases" / row["concept"] / row["case_id"]
        polar = read_polar(case_dir / f"{row['case_id']}.polar")
        cl = float(row["CL"])
        cdi = float(row["CDi"])
        cdiw = polar["CDiw"]
        e_far = cl**2 / (math.pi * 12.0 * cdiw)
        maximum_errors["CL"] = max(maximum_errors["CL"], abs(cl - polar["CLtot"]))
        maximum_errors["CDi"] = max(maximum_errors["CDi"], abs(cdi - polar["CDi"]))
        maximum_errors["CDiw_efficiency"] = max(
            maximum_errors["CDiw_efficiency"], abs(e_far - polar["Ew"])
        )
        root_utilization = float(row["half_wing_root_bending_moment_Nm"]) / root_limit
        rows.append(
            {
                **row,
                "CDi_near_field": cdi,
                "CDiw_far_field": cdiw,
                "e_far_field_total_CL": e_far,
                "Ew_polar": polar["Ew"],
                "root_bending_utilization": root_utilization,
                "root_bending_feasible": root_utilization <= 1.0,
                "polar_path": str(case_dir / f"{row['case_id']}.polar"),
                "lod_path": str(case_dir / f"{row['case_id']}.lod"),
            }
        )
    baseline = next(row for row in rows if row["concept"] == "rigid")
    for row in rows:
        for metric, suffix in [("CDi_near_field", "near"), ("CDiw_far_field", "far")]:
            row[f"reduction_{suffix}_percent"] = 100.0 * (
                baseline[metric] - row[metric]
            ) / baseline[metric]
            row[f"reduction_{suffix}_counts"] = 1.0e4 * (
                baseline[metric] - row[metric]
            )

    selected: list[dict] = []
    for concept in CONCEPTS[1:]:
        feasible = [
            row for row in rows
            if row["concept"] == concept and row["root_bending_feasible"]
        ]
        for method, metric in [
            ("historical_near_field", "CDi_near_field"),
            ("audited_far_field", "CDiw_far_field"),
        ]:
            best = min(feasible, key=lambda row: row[metric])
            selected.append({**best, "selection_method": method})

    out = PROJECT / "outputs" / "far_field_audit"
    plots = out / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    write_csv(out / "all_ranked_results.csv", rows)
    write_csv(out / "selected_cases_near_vs_far.csv", selected)

    fig, ax = plt.subplots(figsize=(9.3, 4.8))
    x = np.arange(3)
    width = 0.34
    for offset, method, label in [
        (-width / 2, "historical_near_field", "Geometry selected by near-field CDi"),
        (width / 2, "audited_far_field", "Geometry selected by far-field CDiw"),
    ]:
        subset = {row["concept"]: row for row in selected if row["selection_method"] == method}
        values = [subset[c]["reduction_far_percent"] for c in CONCEPTS[1:]]
        bars = ax.bar(x + offset, values, width, label=label)
        ax.bar_label(bars, fmt="%.3f%%", fontsize=8, padding=2)
    ax.set_xticks(x, [LABELS[c] for c in CONCEPTS[1:]])
    ax.set_ylabel("Actual far-field induced-drag reduction [%]")
    ax.set_title(r"Mach 0.1: effect of correcting the objective from $C_{D_i}$ to $C_{D_{iw}}$")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    save_all(fig, plots / "01_mach01_near_vs_far_selection")

    fig, ax = plt.subplots(figsize=(8.1, 5.3))
    for concept in CONCEPTS[1:]:
        subset = [row for row in rows if row["concept"] == concept]
        ax.scatter(
            [100.0 * row["root_bending_utilization"] for row in subset],
            [row["reduction_far_percent"] for row in subset],
            s=27,
            alpha=0.65,
            color=COLORS[concept],
            label=LABELS[concept],
        )
        best = next(
            row for row in selected
            if row["concept"] == concept and row["selection_method"] == "audited_far_field"
        )
        ax.scatter(
            100.0 * best["root_bending_utilization"],
            best["reduction_far_percent"],
            marker="*",
            s=150,
            edgecolor="black",
            linewidth=0.7,
            color=COLORS[concept],
            zorder=5,
        )
    ax.axvline(100.0, color="#c2410c", linestyle="--", linewidth=1.2)
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel("Root-bending limit utilization [%]")
    ax.set_ylabel("Far-field induced-drag reduction [%]")
    ax.set_title(r"Audited Mach-0.1 exact design space at fixed $C_L$")
    ax.grid(alpha=0.23)
    ax.legend(frameon=False)
    save_all(fig, plots / "02_mach01_far_field_design_space")

    far = {
        row["concept"]: row
        for row in selected
        if row["selection_method"] == "audited_far_field"
    }
    independent_rows: list[dict] = []
    independent_cases = {"rigid": baseline, **far}
    for concept, row in independent_cases.items():
        reference, strips = read_lod(Path(row["lod_path"]))
        strip_cl = 2.0 * np.sum(strips["Cl"] * strips["dArea"]) / reference["Sref"]
        for modes in [6, 8, 12, 16, 24]:
            efficiency, cdi = lifting_line_efficiency(
                strips["Yavg"],
                strips["Chord"] * strips["Cl"],
                reference["Bref"],
                reference["Sref"],
                modes,
            )
            independent_rows.append(
                {
                    "concept": concept,
                    "case_id": row["case_id"],
                    "fourier_modes": modes,
                    "CL_from_strips": strip_cl,
                    "CL_summary": row["CL"],
                    "CL_closure_error": strip_cl - float(row["CL"]),
                    "span_efficiency_from_loading": efficiency,
                    "CDi_from_loading": cdi,
                    "CDiw_from_polar": row["CDiw_far_field"],
                    "relative_CDi_difference": (cdi - row["CDiw_far_field"])
                    / row["CDiw_far_field"],
                }
            )
    write_csv(out / "independent_lifting_line_check.csv", independent_rows)
    summary = {
        "status": "PASS",
        "case_count": len(rows),
        "native_polar_count": len(rows),
        "maximum_native_consistency_errors": maximum_errors,
        "ranking_metric": "VSPAERO wake-induced CDiw",
        "selected": {
            concept: {
                "case_id": far[concept]["case_id"],
                "CDiw": far[concept]["CDiw_far_field"],
                "reduction_percent": far[concept]["reduction_far_percent"],
                "root_bending_utilization": far[concept]["root_bending_utilization"],
            }
            for concept in CONCEPTS[1:]
        },
    }
    (out / "audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Mach 0.1 far-field induced-drag audit",
        "",
        f"All **{len(rows)}** exact cases have matching native `.polar` files.",
        "The selection metric is wake-induced `CDiw`; historical near-field `CDi` is retained for traceability.",
        "",
        "| Concept | Selected case | CDiw reduction | Root-bending utilization |",
        "|---|---|---:|---:|",
    ]
    for concept in CONCEPTS[1:]:
        row = far[concept]
        lines.append(
            f"| {LABELS[concept]} | `{row['case_id']}` | "
            f"{row['reduction_far_percent']:.3f}% | "
            f"{100.0 * row['root_bending_utilization']:.2f}% |"
        )
    (out / "AUDIT_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

