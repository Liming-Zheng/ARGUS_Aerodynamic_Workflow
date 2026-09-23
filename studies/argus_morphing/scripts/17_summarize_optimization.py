from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(__file__).resolve().parents[1]
BLUE = "#174A6B"
GREEN = "#4E8B57"
ORANGE = "#C56A32"
RED = "#B4473F"
PURPLE = "#785B9E"


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save(fig, output, name):
    fig.savefig(output / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(output / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def nondominated(rows):
    ordered = sorted(rows, key=lambda row: float(row["root_bending_increase_percent"]))
    selected = []
    best_cdi = float("inf")
    for row in ordered:
        cdi = float(row["CDi"])
        if cdi < best_cdi:
            selected.append(row)
            best_cdi = cdi
    return selected


def main():
    output = PROJECT / "outputs" / "optimization"
    config = json.loads((PROJECT / "config" / "optimization_config.json").read_text())
    rows = read_csv(output / "optimization_samples.csv")
    baseline = next(
        row for row in read_csv(
            PROJECT / "outputs" / "exact_trim_loads" / "exact_trim_load_summary.csv"
        )
        if row["case_id"] == "refined_baseline"
    )
    baseline_cdi = float(baseline["CDi"])
    for row in rows:
        row["CDi_reduction_percent"] = 100.0 * (
            baseline_cdi - float(row["CDi"])
        ) / baseline_cdi
        row["feasible_strict"] = (
            float(row["root_bending_increase_percent"])
            <= config["root_bending_increase_limit_percent"]
            and abs(float(row["hinge_torque_proxy_Nm"]))
            <= config["hinge_torque_proxy_limit_Nm"]
            and float(row["max_adjacent_delta"])
            <= config["max_adjacent_delta"]
        )
    feasible = [row for row in rows if row["feasible_strict"]]
    pareto = nondominated(feasible)
    best = min(feasible, key=lambda row: float(row["CDi"]))
    write_csv(output / "exact_feasible_samples.csv", feasible)
    write_csv(output / "exact_pareto_front.csv", pareto)

    fig, ax = plt.subplots(figsize=(9, 5.7))
    infeasible = [row for row in rows if not row["feasible_strict"]]
    ax.scatter(
        [float(row["root_bending_increase_percent"]) for row in infeasible],
        [float(row["CDi"]) for row in infeasible],
        color=RED,
        marker="x",
        s=55,
        label="Infeasible exact samples",
    )
    ax.scatter(
        [float(row["root_bending_increase_percent"]) for row in feasible],
        [float(row["CDi"]) for row in feasible],
        color=BLUE,
        s=45,
        label="Feasible exact samples",
    )
    ax.plot(
        [float(row["root_bending_increase_percent"]) for row in pareto],
        [float(row["CDi"]) for row in pareto],
        color=GREEN,
        marker="o",
        lw=2,
        label="Exact Pareto front",
    )
    ax.scatter(
        float(best["root_bending_increase_percent"]),
        float(best["CDi"]),
        color=ORANGE,
        marker="*",
        s=180,
        label=f"Best feasible: {best['case_id']}",
        zorder=5,
    )
    ax.axvline(config["root_bending_increase_limit_percent"], color=ORANGE, ls="--")
    ax.set_xlabel("Half-wing root bending increase [%]")
    ax.set_ylabel("CDi at fixed CL")
    ax.set_title("ARGUS exact first-round optimization results")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    save(fig, output, "exact_optimization_pareto")

    candidates = [row for row in rows if row["case_id"].startswith("opt_c")]
    predictions = {
        f"opt_c{index:03d}": row
        for index, row in enumerate(read_csv(output / "surrogate_candidates.csv"), start=1)
    }
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    ids = [row["case_id"] for row in candidates]
    x = list(range(len(ids)))
    pred_cdi = [float(predictions[case_id]["predicted_CDi"]) for case_id in ids]
    exact_cdi = [float(row["CDi"]) for row in candidates]
    pred_bending = [
        float(predictions[case_id]["predicted_root_bending_increase_percent"])
        for case_id in ids
    ]
    exact_bending = [float(row["root_bending_increase_percent"]) for row in candidates]
    width = 0.36
    axes[0].bar([i - width / 2 for i in x], pred_cdi, width, color=PURPLE, label="Predicted")
    axes[0].bar([i + width / 2 for i in x], exact_cdi, width, color=GREEN, label="Exact")
    axes[0].set_xticks(x, ids)
    axes[0].set_ylabel("CDi")
    axes[0].set_title("Surrogate validation: induced drag")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar([i - width / 2 for i in x], pred_bending, width, color=PURPLE, label="Predicted")
    axes[1].bar([i + width / 2 for i in x], exact_bending, width, color=GREEN, label="Exact")
    axes[1].axhline(7.0, color=ORANGE, ls="--", label="7% limit")
    axes[1].set_xticks(x, ids)
    axes[1].set_ylabel("Root bending increase [%]")
    axes[1].set_title("Surrogate validation: structural load")
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.25)
    save(fig, output, "surrogate_prediction_validation")

    design = json.loads(
        (
            output
            / "samples"
            / best["case_id"]
            / f"{best['case_id']}_design.json"
        ).read_text()
    )
    report = [
        "ARGUS first-round optimization summary",
        "",
        f"Evaluated designs: {len(rows)}",
        f"Strictly feasible designs: {len(feasible)}",
        f"Exact Pareto designs: {len(pareto)}",
        "",
        "Best feasible design:",
        f"case_id: {best['case_id']}",
        f"control etas: {design['control_etas']}",
        f"control amplitudes A/c: {design['control_amplitudes_over_c']}",
        f"CDi: {float(best['CDi']):.9f}",
        f"CDi reduction vs refined baseline: {float(best['CDi_reduction_percent']):.3f} %",
        f"root bending increase: {float(best['root_bending_increase_percent']):.3f} %",
        f"hinge torque proxy: {float(best['hinge_torque_proxy_Nm']):.3f} N m",
        f"trim alpha: {float(best['alpha_trim_deg']):.6f} deg",
        "",
        "Next active-learning region:",
        "Concentrate new samples near 5.8-7.0% root-bending increase and",
        "A/c schedules similar to the exact Pareto designs.",
    ]
    (output / "first_round_optimization_summary.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    print("\n".join(report))


if __name__ == "__main__":
    main()

