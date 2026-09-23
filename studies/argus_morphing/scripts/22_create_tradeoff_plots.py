from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
BLUE = "#174A6B"
GREEN = "#4E8B57"
TEAL = "#237A72"
ORANGE = "#C56A32"
RED = "#B4473F"
PURPLE = "#785B9E"
GRAY = "#5B6670"

KEY_CASES = {
    "usr_i003_c03": "phase-1 min CDi",
    "ph2b_i001_c03": "phase-2 smooth",
    "opt_s002": "uniform 0.02",
    "opt_s011": "min CDi feasible",
}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(row: dict, key: str, default=0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def save(fig, output: Path, name: str):
    fig.savefig(output / f"{name}.png", dpi=240, bbox_inches="tight")
    fig.savefig(output / f"{name}.svg", bbox_inches="tight")
    fig.savefig(output / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def control_values(row: dict) -> np.ndarray:
    return np.asarray([number(row, f"A{i}_over_c") for i in range(1, 6)])


def roughness(row: dict) -> float:
    values = control_values(row)
    endpoint = values[0] ** 2 + values[-1] ** 2
    curvature = float(np.sum(np.diff(values, n=2) ** 2)) if values.size >= 3 else 0.0
    return float(endpoint + 4.0 * curvature)


def load_rows() -> list[dict]:
    samples = {row["case_id"]: row for row in read_csv(PROJECT / "outputs" / "optimization" / "optimization_samples.csv")}
    # Prefer strict validation values when available for key candidates.
    for case_id in KEY_CASES:
        strict = PROJECT / "outputs" / "final_design_package" / case_id / f"{case_id}_optimization_result.csv"
        if strict.exists():
            samples[case_id] = read_csv(strict)[0]
    baseline = next(
        row for row in read_csv(PROJECT / "outputs" / "exact_trim_loads" / "exact_trim_load_summary.csv")
        if row["case_id"] == "refined_baseline"
    )
    baseline_cdi = number(baseline, "CDi")
    rows = []
    for row in samples.values():
        if not row.get("CDi"):
            continue
        item = dict(row)
        item["CDi_reduction_percent"] = 100.0 * (baseline_cdi - number(row, "CDi")) / baseline_cdi
        item["abs_torque_proxy_Nm"] = abs(number(row, "hinge_torque_proxy_Nm"))
        item["shape_roughness"] = roughness(row)
        item["strict_or_search_feasible"] = (
            number(row, "root_bending_increase_percent", 1e9) <= 6.8
            and abs(number(row, "hinge_torque_proxy_Nm", 1e9)) <= 1050.0
            and number(row, "max_adjacent_delta", 1e9) <= 0.018
        )
        rows.append(item)
    return rows


def scatter_panel(ax, rows, x_key, y_key, xlabel, ylabel, color_key=None):
    feasible = [row for row in rows if row["strict_or_search_feasible"]]
    infeasible = [row for row in rows if not row["strict_or_search_feasible"]]
    if color_key:
        values = [number(row, color_key) for row in feasible]
        sc = ax.scatter(
            [number(row, x_key) for row in feasible],
            [number(row, y_key) for row in feasible],
            c=values,
            cmap="viridis",
            s=48,
            edgecolor="white",
            linewidth=0.6,
            label="Feasible",
            zorder=3,
        )
        plt.colorbar(sc, ax=ax, label=color_key.replace("_", " "))
    else:
        ax.scatter(
            [number(row, x_key) for row in feasible],
            [number(row, y_key) for row in feasible],
            color=BLUE,
            s=48,
            edgecolor="white",
            linewidth=0.6,
            label="Feasible",
            zorder=3,
        )
    ax.scatter(
        [number(row, x_key) for row in infeasible],
        [number(row, y_key) for row in infeasible],
        color=RED,
        marker="x",
        s=52,
        label="Infeasible",
        zorder=2,
    )
    for case_id, label in KEY_CASES.items():
        match = next((row for row in rows if row["case_id"] == case_id), None)
        if not match:
            continue
        ax.scatter(
            number(match, x_key),
            number(match, y_key),
            color=ORANGE if case_id != "ph2b_i001_c03" else GREEN,
            marker="*",
            s=190,
            edgecolor="black",
            linewidth=0.7,
            zorder=5,
        )
        ax.annotate(
            label,
            (number(match, x_key), number(match, y_key)),
            xytext=(7, 6),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.24)


def make_plots(output: Path, rows: list[dict]):
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.0), constrained_layout=True)
    scatter_panel(
        axes[0, 0],
        rows,
        "root_bending_increase_percent",
        "CDi_reduction_percent",
        "Root bending increase [%]",
        "CDi reduction [%]",
        "max_adjacent_delta",
    )
    axes[0, 0].axvline(6.8, color=ORANGE, ls="--", lw=1.3, label="Phase-2 limit")
    scatter_panel(
        axes[0, 1],
        rows,
        "abs_torque_proxy_Nm",
        "CDi_reduction_percent",
        "|Torque proxy| [N m]",
        "CDi reduction [%]",
        "root_bending_increase_percent",
    )
    axes[0, 1].axvline(1050.0, color=ORANGE, ls="--", lw=1.3)
    scatter_panel(
        axes[1, 0],
        rows,
        "max_adjacent_delta",
        "CDi_reduction_percent",
        "Maximum adjacent delta A/c",
        "CDi reduction [%]",
        "root_bending_increase_percent",
    )
    axes[1, 0].axvline(0.018, color=ORANGE, ls="--", lw=1.3)
    scatter_panel(
        axes[1, 1],
        rows,
        "shape_roughness",
        "CDi_reduction_percent",
        "Shape roughness metric",
        "CDi reduction [%]",
        "root_bending_increase_percent",
    )
    axes[0, 0].legend(fontsize=8, loc="best")
    fig.suptitle("ARGUS exact-sample trade-off space", fontsize=16, weight="bold")
    save(fig, output, "multiobjective_tradeoff_space")

    fig, ax = plt.subplots(figsize=(9.0, 6.0), constrained_layout=True)
    scatter_panel(
        ax,
        rows,
        "root_bending_increase_percent",
        "abs_torque_proxy_Nm",
        "Root bending increase [%]",
        "|Torque proxy| [N m]",
        "CDi_reduction_percent",
    )
    ax.axvline(6.8, color=ORANGE, ls="--", lw=1.3)
    ax.axhline(1050.0, color=ORANGE, ls="--", lw=1.3)
    ax.set_title("Structural and actuator-load proxy trade-off")
    save(fig, output, "load_proxy_tradeoff")


def write_summary(output: Path, rows: list[dict]):
    selected = [row for row in rows if row["case_id"] in KEY_CASES]
    fields = [
        "case_id",
        "CDi",
        "CDi_reduction_percent",
        "root_bending_increase_percent",
        "hinge_torque_proxy_Nm",
        "max_adjacent_delta",
        "shape_roughness",
        "strict_or_search_feasible",
    ]
    with (output / "tradeoff_key_cases.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in selected:
            writer.writerow({key: row.get(key, "") for key in fields})
    text = """# ARGUS trade-off plot package

This package uses the current exact VSPAERO sample pool plus strict validation
values for key candidates when available.

- `multiobjective_tradeoff_space`: CDi benefit versus root bending, torque,
  adjacent morphing jump, and shape roughness.
- `load_proxy_tradeoff`: root bending versus actuator torque proxy.

Star markers identify important candidates:

- `usr_i003_c03`: phase-1 minimum-CDi candidate, slightly infeasible after strict validation.
- `ph2b_i001_c03`: current preferred smooth, strict-feasible phase-2 candidate.
- `opt_s002`: uniform A/c=0.02 reference.
- `opt_s011`: best minimum-CDi feasible candidate under the current sample-pool filter.
"""
    (output / "README_tradeoff_plots.md").write_text(text, encoding="utf-8")


def main():
    output = PROJECT / "outputs" / "tradeoff_plots"
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })
    rows = load_rows()
    make_plots(output, rows)
    write_summary(output, rows)
    print(f"Wrote trade-off plots to {output}")


if __name__ == "__main__":
    main()

