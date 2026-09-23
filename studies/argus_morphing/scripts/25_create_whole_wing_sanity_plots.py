from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
BLUE = "#174A6B"
GREEN = "#4E8B57"
ORANGE = "#C56A32"
GRAY = "#5B6670"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, float | str]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_distribution(path: Path) -> dict[str, np.ndarray]:
    rows = read_csv(path)
    dy_name = "dy" if "dy" in rows[0] else "dy_m"
    eta = np.asarray([float(row["eta"]) for row in rows], dtype=float)
    dy = np.asarray([float(row[dy_name]) for row in rows], dtype=float)
    lift = np.asarray([float(row["lift_per_span_N_per_m"]) for row in rows], dtype=float)
    order = np.argsort(eta)
    return {"eta": eta[order], "dy": dy[order], "lift": lift[order]}


def integrated_lift(data: dict[str, np.ndarray]) -> float:
    return float(np.sum(data["lift"] * data["dy"]))


def elliptical_reference(eta: np.ndarray, dy: np.ndarray, total_lift: float) -> np.ndarray:
    shape = np.sqrt(np.clip(1.0 - eta**2, 0.0, None))
    scale = total_lift / float(np.sum(shape * dy))
    return scale * shape


def normalized_error(
    data: dict[str, np.ndarray],
    reference_lift: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    total = integrated_lift(data)
    normalized = data["lift"] / total
    reference = reference_lift / float(np.sum(reference_lift * data["dy"]))
    error = float(np.sqrt(np.average((normalized - reference) ** 2, weights=data["dy"])))
    return error, normalized, reference


def interpolate_to(eta_source: np.ndarray, values: np.ndarray, eta_target: np.ndarray) -> np.ndarray:
    return np.interp(eta_target, eta_source, values)


def main() -> None:
    output = PROJECT / "plot" / "whole_wing_sanity"
    output.mkdir(parents=True, exist_ok=True)

    baseline_path = PROJECT / "outputs" / "exact_trim_loads" / "refined_baseline_spanwise_load.csv"
    best_case = "wsu_i002_c02"
    best_path = (
        PROJECT
        / "outputs"
        / "optimization"
        / "samples"
        / best_case
        / f"{best_case}_spanwise_loads.csv"
    )
    baseline_result = read_csv(
        PROJECT / "outputs" / "exact_trim_loads" / "refined_baseline_exact_trim.csv"
    )[0]
    best_result = read_csv(
        PROJECT
        / "outputs"
        / "optimization"
        / "samples"
        / best_case
        / f"{best_case}_optimization_result.csv"
    )[0]

    baseline = load_distribution(baseline_path)
    best = load_distribution(best_path)
    ellipse_best = elliptical_reference(best["eta"], best["dy"], integrated_lift(best))
    ellipse_on_baseline = interpolate_to(best["eta"], ellipse_best, baseline["eta"])

    baseline_error, baseline_norm, ellipse_baseline_norm = normalized_error(
        baseline,
        ellipse_on_baseline,
    )
    best_error, best_norm, ellipse_best_norm = normalized_error(best, ellipse_best)

    summary = {
        "baseline_case": "refined_baseline",
        "best_case": best_case,
        "baseline_CDi": float(baseline_result["CDi"]),
        "best_CDi": float(best_result["CDi"]),
        "CDi_reduction_percent": 100.0
        * (float(baseline_result["CDi"]) - float(best_result["CDi"]))
        / float(baseline_result["CDi"]),
        "baseline_elliptic_rms_error": baseline_error,
        "best_elliptic_rms_error": best_error,
        "elliptic_error_reduction_percent": 100.0
        * (baseline_error - best_error)
        / baseline_error,
        "best_alpha_trim_deg": float(best_result["alpha_trim_deg"]),
        "best_CL_error": float(best_result["CL_error"]),
        "best_root_bending_increase_percent": float(best_result["root_bending_increase_percent"]),
        "best_max_adjacent_delta": float(best_result["max_adjacent_delta"]),
    }
    (output / "whole_wing_sanity_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    rows = []
    best_lift_on_baseline = interpolate_to(best["eta"], best["lift"], baseline["eta"])
    for eta, base_lift, opt_lift, ellipse_lift in zip(
        baseline["eta"],
        baseline["lift"],
        best_lift_on_baseline,
        ellipse_on_baseline,
    ):
        rows.append({
            "eta": eta,
            "baseline_lift_per_span_N_per_m": base_lift,
            "optimized_lift_per_span_N_per_m": opt_lift,
            "elliptical_reference_lift_per_span_N_per_m": ellipse_lift,
        })
    write_csv(output / "whole_wing_sanity_lift_distribution.csv", rows)

    plt.rcParams["svg.fonttype"] = "none"
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    ax.plot(
        baseline["eta"],
        baseline["lift"],
        color=GRAY,
        lw=2.0,
        label="Baseline",
    )
    ax.plot(
        best["eta"],
        best["lift"],
        color=GREEN,
        lw=2.4,
        label=f"Optimized ({best_case})",
    )
    ax.plot(
        best["eta"],
        ellipse_best,
        color=ORANGE,
        lw=2.0,
        ls="--",
        label="Elliptical reference",
    )
    ax.set_xlabel(r"$\eta=y/(b/2)$")
    ax.set_ylabel("Lift per span [N/m]")
    ax.set_title("Whole-wing sanity check: spanwise lift distribution")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.savefig(output / "whole_wing_sanity_lift_distribution.svg", bbox_inches="tight")
    fig.savefig(output / "whole_wing_sanity_lift_distribution.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    ax.plot(
        baseline["eta"],
        baseline_norm,
        color=GRAY,
        lw=2.0,
        label=f"Baseline, RMS={baseline_error:.4e}",
    )
    ax.plot(
        best["eta"],
        best_norm,
        color=GREEN,
        lw=2.4,
        label=f"Optimized, RMS={best_error:.4e}",
    )
    ax.plot(
        best["eta"],
        ellipse_best_norm,
        color=ORANGE,
        lw=2.0,
        ls="--",
        label="Elliptical reference",
    )
    ax.set_xlabel(r"$\eta=y/(b/2)$")
    ax.set_ylabel("Normalized lift density [1/m]")
    ax.set_title("Normalized lift-distribution error to elliptical reference")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.savefig(output / "whole_wing_sanity_elliptic_error.svg", bbox_inches="tight")
    fig.savefig(output / "whole_wing_sanity_elliptic_error.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    bars = ax.bar(
        ["Baseline", "Optimized"],
        [baseline_error, best_error],
        color=[GRAY, BLUE],
    )
    ax.bar_label(bars, fmt="%.4e", padding=3, fontsize=9)
    ax.set_ylabel("Weighted RMS error to ellipse")
    ax.set_title("Elliptical lift-distribution sanity metric")
    ax.grid(axis="y", alpha=0.25)
    fig.savefig(output / "whole_wing_sanity_error_metric.svg", bbox_inches="tight")
    fig.savefig(output / "whole_wing_sanity_error_metric.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

