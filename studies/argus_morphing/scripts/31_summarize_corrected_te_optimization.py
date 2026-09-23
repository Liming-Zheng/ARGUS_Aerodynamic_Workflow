from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "plot" / "corrected_te_optimization"
BLUE = "#174A6B"
GREEN = "#4E8B57"
ORANGE = "#C56A32"
RED = "#B4473F"
PURPLE = "#785B9E"
GRAY = "#5B6670"


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_one(path):
    return read_csv(path)[0]


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save(fig, name):
    fig.savefig(OUTPUT / f"{name}.png", dpi=240, bbox_inches="tight")
    fig.savefig(OUTPUT / f"{name}.svg", bbox_inches="tight")
    fig.savefig(OUTPUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def number(row, key):
    return float(row[key])


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    baseline_dir = (
        PROJECT
        / "outputs"
        / "tyler_validation_2026_07_29"
        / "baseline_corrected"
    )
    unchanged_dir = (
        PROJECT
        / "outputs"
        / "tyler_validation_2026_07_29"
        / "mcv2_i002_c01"
    )
    strict_dir = (
        PROJECT / "outputs" / "corrected_te_validation" / "cte_i002_c04"
    )
    optimization_root = PROJECT / "outputs" / "corrected_te_optimization"
    run_root = optimization_root / "corrected_te_cdi"

    baseline = read_one(
        baseline_dir / "baseline_corrected_optimization_result.csv"
    )
    unchanged = read_one(
        unchanged_dir / "mcv2_i002_c01_optimization_result.csv"
    )
    best = read_one(strict_dir / "cte_i002_c04_optimization_result.csv")
    design = json.loads(
        (strict_dir / "cte_i002_c04_design.json").read_text(encoding="utf-8")
    )
    history = read_csv(run_root / "iteration_history.csv")
    samples = read_csv(optimization_root / "optimization_samples.csv")

    baseline_cdi = number(baseline, "CDi")
    baseline_bending = number(baseline, "root_bending_moment_Nm")
    rows = []
    for label, result in [
        ("Corrected rigid baseline", baseline),
        ("Unchanged pre-correction command", unchanged),
        ("Corrected optimized candidate", best),
    ]:
        cdi = number(result, "CDi")
        bending = number(result, "root_bending_moment_Nm")
        rows.append(
            {
                "label": label,
                "case_id": result["case_id"],
                "trim_mode": result["trim_mode"],
                "alpha_trim_deg": number(result, "alpha_trim_deg"),
                "CL": number(result, "CL"),
                "CL_error": number(result, "CL_error"),
                "CDi": cdi,
                "CDi_delta_counts_vs_corrected_baseline": 10000.0
                * (cdi - baseline_cdi),
                "CDi_reduction_percent_vs_corrected_baseline": 100.0
                * (baseline_cdi - cdi)
                / baseline_cdi,
                "half_wing_root_bending_Nm": bending,
                "root_bending_change_percent_vs_corrected_baseline": 100.0
                * (bending - baseline_bending)
                / baseline_bending,
                "max_adjacent_delta": number(result, "max_adjacent_delta"),
            }
        )
    write_csv(OUTPUT / "corrected_te_strict_summary.csv", rows)

    plt.rcParams["svg.fonttype"] = "none"
    iterations = [int(row["iteration"]) for row in history]
    best_cdi = [float(row["best_metric_after"]) for row in history]
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    ax.plot(iterations, best_cdi, color=BLUE, marker="o", lw=2.2)
    for x_value, y_value in zip(iterations, best_cdi):
        ax.annotate(
            f"{y_value:.7f}",
            (x_value, y_value),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    ax.set_xlabel("Outer optimization iteration")
    ax.set_ylabel(r"Best exact $C_{D_i}$")
    ax.set_title("Corrected trailing-edge optimization convergence")
    ax.set_xticks(iterations)
    ax.grid(alpha=0.25)
    save(fig, "01_corrected_te_convergence")

    feasible = [
        row
        for row in samples
        if number(row, "root_bending_increase_percent") <= 6.8
        and number(row, "max_adjacent_delta") <= 0.018
    ]
    infeasible = [row for row in samples if row not in feasible]
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    ax.scatter(
        [number(row, "root_bending_increase_percent") for row in feasible],
        [number(row, "CDi") for row in feasible],
        color=BLUE,
        label="Feasible exact samples",
    )
    ax.scatter(
        [number(row, "root_bending_increase_percent") for row in infeasible],
        [number(row, "CDi") for row in infeasible],
        color=RED,
        marker="x",
        label="Rejected exact samples",
    )
    ax.scatter(
        number(best, "root_bending_increase_percent"),
        number(best, "CDi"),
        color=ORANGE,
        marker="*",
        s=190,
        zorder=5,
        label="Strict best cte_i002_c04",
    )
    ax.axvline(6.8, color=ORANGE, ls="--", label="Illustrative bending screen")
    ax.set_xlabel("Half-wing root-bending increase [%]")
    ax.set_ylabel(r"$C_{D_i}$ at fixed lift")
    ax.set_title("Corrected exact design space")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    save(fig, "02_corrected_te_design_space")

    unchanged_design = json.loads(
        (unchanged_dir / "mcv2_i002_c01_design.json").read_text(encoding="utf-8")
    )
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    ax.plot(
        unchanged_design["control_etas"],
        unchanged_design["control_amplitudes_over_c"],
        color=GRAY,
        marker="o",
        ls="--",
        label="Unchanged mcv2 command",
    )
    ax.plot(
        design["control_etas"],
        design["control_amplitudes_over_c"],
        color=GREEN,
        marker="o",
        lw=2.2,
        label="Corrected optimized command",
    )
    ax.axhline(0.0, color="#999999", lw=0.8)
    ax.set_xlabel(r"Semi-span coordinate $\eta$")
    ax.set_ylabel(r"Morphing amplitude $A/c$")
    ax.set_title("Command schedule after corrected-geometry reoptimization")
    ax.grid(alpha=0.25)
    ax.legend()
    save(fig, "03_corrected_te_schedule")

    load_sets = [
        (
            "Corrected baseline",
            read_csv(baseline_dir / "baseline_corrected_spanwise_loads.csv"),
            GRAY,
            "--",
        ),
        (
            "Unchanged mcv2 command",
            read_csv(unchanged_dir / "mcv2_i002_c01_spanwise_loads.csv"),
            PURPLE,
            ":",
        ),
        (
            "Corrected optimized candidate",
            read_csv(strict_dir / "cte_i002_c04_spanwise_loads.csv"),
            GREEN,
            "-",
        ),
    ]
    fig, axes = plt.subplots(2, 1, figsize=(9.0, 7.2), sharex=True)
    for label, loads, color, line_style in load_sets:
        eta = [number(row, "eta") for row in loads]
        axes[0].plot(
            eta,
            [number(row, "lift_per_span_N_per_m") for row in loads],
            color=color,
            ls=line_style,
            lw=2.0,
            label=label,
        )
        axes[1].plot(
            eta,
            [number(row, "sectional_cl") for row in loads],
            color=color,
            ls=line_style,
            lw=2.0,
        )
    for axis in axes:
        axis.axvspan(0.6, 1.0, color="#DDEADF", alpha=0.35)
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Lift per span [N/m]")
    axes[0].legend(fontsize=8)
    axes[0].set_title("Strict spanwise load redistribution")
    axes[1].set_ylabel(r"Sectional $c_l$")
    axes[1].set_xlabel(r"Semi-span coordinate $\eta$")
    save(fig, "04_corrected_te_spanwise_loads")

    labels = ["Unchanged\nmcv2", "Corrected\noptimum"]
    drag_reductions = [
        rows[1]["CDi_reduction_percent_vs_corrected_baseline"],
        rows[2]["CDi_reduction_percent_vs_corrected_baseline"],
    ]
    bending_changes = [
        rows[1]["root_bending_change_percent_vs_corrected_baseline"],
        rows[2]["root_bending_change_percent_vs_corrected_baseline"],
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.8))
    bars = axes[0].bar(labels, drag_reductions, color=[PURPLE, GREEN])
    axes[0].bar_label(bars, fmt="%.2f%%", padding=3)
    axes[0].set_ylabel(r"$C_{D_i}$ reduction [%]")
    axes[0].set_title("Aerodynamic benefit")
    axes[0].grid(axis="y", alpha=0.25)
    bars = axes[1].bar(labels, bending_changes, color=[PURPLE, GREEN])
    axes[1].bar_label(bars, fmt="%.2f%%", padding=3)
    axes[1].axhline(6.8, color=ORANGE, ls="--", label="6.8% screen")
    axes[1].set_ylabel("Root-bending increase [%]")
    axes[1].set_title("Constraint response")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(fontsize=8)
    save(fig, "05_corrected_te_key_metrics")

    optimized = rows[2]
    summary = {
        "case_id": optimized["case_id"],
        "strict_CDi": optimized["CDi"],
        "CDi_reduction_percent": optimized[
            "CDi_reduction_percent_vs_corrected_baseline"
        ],
        "CDi_delta_counts": optimized[
            "CDi_delta_counts_vs_corrected_baseline"
        ],
        "root_bending_increase_percent": optimized[
            "root_bending_change_percent_vs_corrected_baseline"
        ],
        "root_bending_limit_percent": 6.8,
        "max_adjacent_delta": optimized["max_adjacent_delta"],
        "max_adjacent_delta_limit": 0.018,
        "root_bending_active": (
            6.8 - optimized["root_bending_change_percent_vs_corrected_baseline"]
            < 0.05
        ),
        "adjacent_command_active": (
            0.018 - optimized["max_adjacent_delta"] < 5.0e-4
        ),
        "exact_samples": len(samples),
        "outer_iterations": len(history) - 1,
    }
    (OUTPUT / "corrected_te_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    english = f"""# Corrected trailing-edge optimization

- Exact VSPAERO samples: {len(samples)}
- Surrogate-assisted outer iterations: {len(history) - 1}
- Strict best: `{summary['case_id']}`
- Strict CDi: {summary['strict_CDi']:.9f}
- Reduction from corrected rigid baseline: {summary['CDi_reduction_percent']:.3f}% ({-summary['CDi_delta_counts']:.3f} drag counts)
- Root-bending increase: {summary['root_bending_increase_percent']:.3f}% against the illustrative 6.8% screen
- Maximum adjacent command: {summary['max_adjacent_delta']:.6f} against 0.018

The corrected optimization recovers a feasible trailing-edge candidate. Root
bending is the active screen. The adjacent-command screen is close but not the
limiting value. The hinge-moment constraint remains disabled and must be
replaced by pressure integration and a traceable mechanical allowable.
"""
    chinese = f"""# 修正几何后的后缘连续变形优化

- VSPAERO 精确样本：{len(samples)} 个
- 代理模型外循环：{len(history) - 1} 轮
- 严格验证最优解：`{summary['case_id']}`
- 严格验证 CDi：{summary['strict_CDi']:.9f}
- 相对修正刚性基准的降低：{summary['CDi_reduction_percent']:.3f}%（{-summary['CDi_delta_counts']:.3f} 个阻力 count）
- 根弯矩增加：{summary['root_bending_increase_percent']:.3f}%，示范性筛选界限为 6.8%
- 最大相邻命令差：{summary['max_adjacent_delta']:.6f}，界限为 0.018

修正几何后的重新优化已经找回满足当前筛选条件的后缘连续变形候选。
根弯矩是 active constraint；相邻命令约束也比较接近，但不是最终限制项。
hinge moment 约束仍保持关闭，后续应使用压力积分结果和可追溯的机械许用值。
"""
    (OUTPUT / "RESULTS_EN.md").write_text(english, encoding="utf-8")
    (OUTPUT / "RESULTS_CN.md").write_text(chinese, encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

