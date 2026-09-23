from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(__file__).resolve().parents[1]
CODEX_WORK = PROJECT.parent
OUTPUT = PROJECT / "plot" / "corrected_twist_optimization"
BASELINE_DIR = (
    CODEX_WORK
    / "argus_morphing"
    / "outputs"
    / "tyler_validation_2026_07_29"
    / "baseline_corrected"
)
TE_DIR = (
    CODEX_WORK
    / "argus_morphing"
    / "outputs"
    / "corrected_te_validation"
    / "cte_i002_c04"
)
TWIST_DIR = PROJECT / "outputs" / "corrected_twist_validation" / "ctw_i001_c03"
SEARCH_ROOT = PROJECT / "outputs" / "corrected_twist_optimization"


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def row(path):
    return read_csv(path)[0]


def floats(rows, key):
    return [float(item[key]) for item in rows]


def save(fig, stem):
    for extension in ["png", "svg", "pdf"]:
        kwargs = {"dpi": 240} if extension == "png" else {}
        fig.savefig(OUTPUT / f"{stem}.{extension}", bbox_inches="tight", **kwargs)
    plt.close(fig)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "svg.fonttype": "none",
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.22,
        }
    )

    baseline = row(BASELINE_DIR / "baseline_corrected_optimization_result.csv")
    trailing_edge = row(TE_DIR / "cte_i002_c04_optimization_result.csv")
    twist = row(TWIST_DIR / "ctw_i001_c03_optimization_result.csv")
    baseline_cdi = float(baseline["CDi"])

    history = read_csv(SEARCH_ROOT / "corrected_twist_cdi" / "iteration_history.csv")
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    ax.plot(
        [int(item["iteration"]) for item in history],
        [float(item["best_metric_after"]) for item in history],
        marker="o",
        lw=2.2,
        color="#174A6B",
    )
    ax.set_xticks([0, 1, 2])
    ax.set_xlabel("Completed surrogate-assisted outer iteration")
    ax.set_ylabel(r"Best exact feasible $C_{D_i}$")
    ax.set_title("Corrected distributed-twist optimization convergence")
    save(fig, "01_corrected_twist_convergence")

    samples = read_csv(SEARCH_ROOT / "optimization_samples.csv")
    feasible = [item for item in samples if item["feasible"].lower() == "true"]
    infeasible = [item for item in samples if item["feasible"].lower() != "true"]
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.scatter(
        floats(feasible, "root_bending_increase_percent"),
        floats(feasible, "CDi"),
        color="#174A6B",
        label="Search-feasible exact samples",
    )
    ax.scatter(
        floats(infeasible, "root_bending_increase_percent"),
        floats(infeasible, "CDi"),
        color="#B4473F",
        marker="x",
        label="Search-infeasible exact samples",
    )
    ax.scatter(
        [float(twist["root_bending_increase_percent"])],
        [float(twist["CDi"])],
        marker="*",
        s=190,
        color="#E69F00",
        edgecolor="black",
        linewidth=0.5,
        label="Strict feasible best: ctw_i001_c03",
        zorder=4,
    )
    ax.axvline(6.8, color="#C56A32", ls="--", label="Root-bending limit")
    ax.set_xlabel("Half-wing root-bending increase [%]")
    ax.set_ylabel(r"$C_{D_i}$")
    ax.set_title("Corrected twist exact design space")
    ax.legend(fontsize=8)
    save(fig, "02_corrected_twist_design_space")

    design = json.loads(
        (TWIST_DIR / "ctw_i001_c03_design.json").read_text(encoding="utf-8")
    )
    schedule = read_csv(TWIST_DIR / "ctw_i001_c03_twist_schedule.csv")
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    ax.plot(
        floats(schedule, "eta"),
        floats(schedule, "incremental_twist_deg"),
        color="#D55E00",
        lw=2.2,
        label="Applied OpenVSP section increment",
    )
    ax.scatter(
        design["control_etas"],
        design["control_twist_deg"],
        color="#174A6B",
        zorder=3,
        label="Five optimization commands",
    )
    ax.axvline(0.6, color="#237A72", ls="--", label="Morphing-region start")
    ax.axhline(0.0, color="#5B6670", lw=0.9)
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel(r"Semi-span coordinate $\eta=y/(b/2)$")
    ax.set_ylabel("Incremental section twist [deg]")
    ax.set_title("Strict feasible distributed-twist schedule")
    ax.legend(fontsize=8)
    save(fig, "03_corrected_twist_schedule")

    load_sets = [
        (
            "Corrected rigid baseline",
            read_csv(BASELINE_DIR / "baseline_corrected_spanwise_loads.csv"),
            "#5B6670",
        ),
        (
            "Corrected trailing edge",
            read_csv(TE_DIR / "cte_i002_c04_spanwise_loads.csv"),
            "#0072B2",
        ),
        (
            "Corrected distributed twist",
            read_csv(TWIST_DIR / "ctw_i001_c03_spanwise_loads.csv"),
            "#D55E00",
        ),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    for label, loads, color in load_sets:
        ax.plot(
            floats(loads, "eta"),
            floats(loads, "lift_per_span_N_per_m"),
            lw=2.0,
            color=color,
            label=label,
        )
    ax.axvspan(0.6, 1.0, color="#7FBF7B", alpha=0.10)
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel(r"Semi-span coordinate $\eta=y/(b/2)$")
    ax.set_ylabel("Lift per unit span [N/m]")
    ax.set_title("Strict fixed-lift spanwise loading on the corrected geometry")
    ax.legend(fontsize=8)
    save(fig, "04_corrected_twist_spanwise_loads")

    concepts = ["Trailing-edge\ncamber", "Distributed\ntwist"]
    result_rows = [trailing_edge, twist]
    reductions = [
        100.0 * (baseline_cdi - float(item["CDi"])) / baseline_cdi
        for item in result_rows
    ]
    bending = [
        100.0 * float(item["root_bending_increase_percent"]) / 6.8
        for item in result_rows
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.7))
    bars = axes[0].bar(concepts, reductions, color=["#0072B2", "#D55E00"])
    axes[0].bar_label(bars, fmt="%.3f%%", padding=3)
    axes[0].set_ylabel(r"$C_{D_i}$ reduction from corrected baseline [%]")
    axes[0].set_title("Aerodynamic benefit")
    bars = axes[1].bar(concepts, bending, color=["#0072B2", "#D55E00"])
    axes[1].bar_label(bars, fmt="%.2f%%", padding=3)
    axes[1].axhline(100.0, color="#B4473F", ls="--", label="Constraint")
    axes[1].set_ylabel("Root-bending constraint utilization [%]")
    axes[1].set_title("Active load screen")
    axes[1].legend(fontsize=8)
    fig.suptitle("Matched corrected low-speed comparison", fontweight="bold")
    save(fig, "05_corrected_te_vs_twist")

    summary = {
        "condition": {
            "mach": 0.1,
            "CL_target": 0.428277635108,
            "morph_region_eta": [0.6, 1.0],
            "root_bending_limit_increase_percent": 6.8,
        },
        "baseline": {
            "case_id": baseline["case_id"],
            "CDi": baseline_cdi,
            "root_bending_moment_Nm": float(baseline["root_bending_moment_Nm"]),
        },
        "trailing_edge": {
            "case_id": trailing_edge["case_id"],
            "CDi": float(trailing_edge["CDi"]),
            "CDi_reduction_percent": reductions[0],
            "root_bending_increase_percent": float(
                trailing_edge["root_bending_increase_percent"]
            ),
        },
        "distributed_twist": {
            "case_id": twist["case_id"],
            "CDi": float(twist["CDi"]),
            "CDi_reduction_percent": reductions[1],
            "drag_count_reduction": 10000.0 * (baseline_cdi - float(twist["CDi"])),
            "root_bending_increase_percent": float(
                twist["root_bending_increase_percent"]
            ),
            "max_adjacent_twist_delta_deg": float(
                twist["max_adjacent_twist_delta_deg"]
            ),
            "strict_feasible": twist["feasible"].lower() == "true",
        },
        "matched_gap": {
            "trailing_edge_minus_twist_CDi": (
                float(trailing_edge["CDi"]) - float(twist["CDi"])
            ),
            "twist_penalty_vs_trailing_edge_drag_counts": 10000.0
            * (float(twist["CDi"]) - float(trailing_edge["CDi"])),
        },
        "search": {
            "seed_samples": 18,
            "outer_iterations": 2,
            "exact_candidates_per_iteration": 4,
            "total_exact_samples": len(samples),
            "strict_rejected_case": "ctw_i002_c04",
            "strict_selected_case": twist["case_id"],
        },
    }
    (OUTPUT / "corrected_twist_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    with (OUTPUT / "corrected_twist_comparison.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "concept",
                "case_id",
                "CDi",
                "CDi_reduction_percent",
                "root_bending_increase_percent",
            ],
        )
        writer.writeheader()
        for concept, item, reduction in zip(
            ["trailing_edge", "distributed_twist"], result_rows, reductions
        ):
            writer.writerow(
                {
                    "concept": concept,
                    "case_id": item["case_id"],
                    "CDi": item["CDi"],
                    "CDi_reduction_percent": reduction,
                    "root_bending_increase_percent": item[
                        "root_bending_increase_percent"
                    ],
                }
            )

    english = f"""# Corrected distributed-twist optimization

- Strict feasible candidate: `{twist['case_id']}`.
- Exact samples: 18 seeds + 2 batches of 4 = 26.
- Fixed condition: Mach 0.1, CL = 0.428277635108.
- CDi: {float(twist['CDi']):.9f}; reduction from corrected baseline: {reductions[1]:.3f}%.
- Root-bending increase: {float(twist['root_bending_increase_percent']):.4f}% (limit 6.8%).
- Maximum adjacent twist command: {float(twist['max_adjacent_twist_delta_deg']):.4f} deg (limit 2.5 deg).
- Corrected trailing-edge camber remains aerodynamically better by {10000.0 * (float(twist['CDi']) - float(trailing_edge['CDi'])):.3f} drag counts at this low-speed condition.

`ctw_i002_c04` was the fast-search best but exceeded the bending limit after strict iterative trim, so it was rejected. Mechanical evidence is still required for down-selection.
"""
    chinese = f"""# 修正后的分布式扭转优化

- 严格验证后的可行候选：`{twist['case_id']}`。
- 精确样本：18 个初始样本 + 两轮、每轮 4 个候选，共 26 个。
- 固定工况：Mach 0.1，CL = 0.428277635108。
- CDi：{float(twist['CDi']):.9f}；相对修正 baseline 降低 {reductions[1]:.3f}%。
- 翼根弯矩增加：{float(twist['root_bending_increase_percent']):.4f}%（限制 6.8%）。
- 最大相邻扭转命令差：{float(twist['max_adjacent_twist_delta_deg']):.4f} 度（限制 2.5 度）。
- 在该低速工况下，修正后的 trailing-edge camber 气动上仍领先 {10000.0 * (float(twist['CDi']) - float(trailing_edge['CDi'])):.3f} drag counts。

`ctw_i002_c04` 是快速搜索阶段的最优点，但严格迭代 trim 后略微超过弯矩限制，因此被拒绝。最终方案下选仍需要机械、结构和驱动证据。
"""
    (OUTPUT / "RESULTS_EN.md").write_text(english, encoding="utf-8")
    (OUTPUT / "RESULTS_ZH.md").write_text(chinese, encoding="utf-8")


if __name__ == "__main__":
    main()

