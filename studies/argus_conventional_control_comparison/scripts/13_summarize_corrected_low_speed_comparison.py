"""Summarize the audited Mach-0.1 rigid/hinged/camber/twist comparison."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "rigid": "#4B5563",
    "hinged": "#B4473F",
    "camber": "#0076A8",
    "twist": "#D97706",
}
LABELS = {
    "rigid": "Rigid baseline",
    "hinged": "Conventional hinged",
    "camber": "Continuous trailing edge",
    "twist": "Distributed twist",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_one(path: Path) -> dict[str, str]:
    rows = read_rows(path)
    if len(rows) != 1:
        raise RuntimeError(f"Expected one row in {path}, found {len(rows)}")
    return rows[0]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save(fig: plt.Figure, output: Path, stem: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for suffix in [".png", ".svg", ".pdf"]:
        fig.savefig(
            output / f"{stem}{suffix}",
            dpi=260 if suffix == ".png" else None,
            bbox_inches="tight",
        )
    plt.close(fig)


def float_value(row: dict[str, str], name: str) -> float:
    return float(row[name])


def load_concepts(repo: Path) -> list[dict]:
    baseline = read_one(
        repo
        / "argus_morphing/outputs/tyler_validation_2026_07_29"
        / "baseline_corrected/baseline_corrected_optimization_result.csv"
    )
    hinged = read_one(
        repo
        / "argus_conventional_control_comparison/outputs"
        / "corrected_low_speed_validation/chc_g02_c17"
        / "chc_g02_c17_optimization_result.csv"
    )
    camber = read_one(
        repo
        / "argus_morphing/outputs/corrected_te_validation/cte_i002_c04"
        / "cte_i002_c04_optimization_result.csv"
    )
    twist = read_one(
        repo
        / "argus_twist_morphing/outputs"
        / "corrected_twist_validation/ctw_i001_c03"
        / "ctw_i001_c03_optimization_result.csv"
    )
    baseline_cdi = float_value(baseline, "CDi")
    baseline_bending = float_value(baseline, "root_bending_moment_Nm")
    source_rows = {
        "rigid": baseline,
        "hinged": hinged,
        "camber": camber,
        "twist": twist,
    }
    case_ids = {
        "rigid": "baseline_corrected",
        "hinged": "chc_g02_c17",
        "camber": "cte_i002_c04",
        "twist": "ctw_i001_c03",
    }
    rows = []
    for concept in ["rigid", "hinged", "camber", "twist"]:
        source = source_rows[concept]
        cdi = float_value(source, "CDi")
        bending = float_value(source, "root_bending_moment_Nm")
        rows.append(
            {
                "concept": concept,
                "label": LABELS[concept],
                "case_id": case_ids[concept],
                "CDi": cdi,
                "CDi_reduction_percent": 100.0 * (baseline_cdi - cdi) / baseline_cdi,
                "CDi_reduction_drag_counts": 10000.0 * (baseline_cdi - cdi),
                "root_bending_moment_Nm": bending,
                "root_bending_increase_percent": 100.0
                * (bending - baseline_bending)
                / baseline_bending,
                "bending_screen_utilization_percent": (
                    0.0
                    if concept == "rigid"
                    else 100.0
                    * (
                        100.0
                        * (bending - baseline_bending)
                        / baseline_bending
                    )
                    / 6.8
                ),
                "strict_feasible": True,
            }
        )
    return rows


def plot_design_space(repo: Path, output: Path, summary: list[dict]) -> None:
    samples = read_rows(
        repo
        / "argus_conventional_control_comparison/outputs"
        / "corrected_low_speed/optimization_samples.csv"
    )
    feasible = [row for row in samples if row["feasible"].lower() == "true"]
    infeasible = [row for row in samples if row["feasible"].lower() != "true"]
    best = next(row for row in summary if row["concept"] == "hinged")

    fig, ax = plt.subplots(figsize=(7.6, 5.1), constrained_layout=True)
    ax.scatter(
        [float_value(row, "root_bending_increase_percent") for row in feasible],
        [float_value(row, "CDi") for row in feasible],
        s=32,
        color=COLORS["hinged"],
        label="Feasible exact sample",
        alpha=0.78,
    )
    ax.scatter(
        [float_value(row, "root_bending_increase_percent") for row in infeasible],
        [float_value(row, "CDi") for row in infeasible],
        s=32,
        marker="x",
        color="#9CA3AF",
        label="Infeasible exact sample",
    )
    ax.scatter(
        [best["root_bending_increase_percent"]],
        [best["CDi"]],
        s=150,
        marker="*",
        color="#F5C242",
        edgecolor="#111827",
        linewidth=0.8,
        label="Strict best: chc_g02_c17",
        zorder=5,
    )
    ax.axvline(6.8, color="#111827", linestyle="--", linewidth=1.2)
    ax.text(6.8, ax.get_ylim()[1], " 6.8% screen", ha="left", va="top")
    ax.set_xlabel("Half-wing root-bending increase [%]")
    ax.set_ylabel(r"$C_{D_i}$")
    ax.set_title("Corrected conventional-control exact design space")
    ax.grid(color="#E5E7EB", linewidth=0.7)
    ax.legend(frameon=False)
    save(fig, output, "01_corrected_hinged_design_space")


def plot_deflection_space(repo: Path, output: Path) -> None:
    samples = read_rows(
        repo
        / "argus_conventional_control_comparison/outputs"
        / "corrected_low_speed/optimization_samples.csv"
    )
    x = np.array([float_value(row, "delta_inboard_deg") for row in samples])
    y = np.array([float_value(row, "delta_outboard_deg") for row in samples])
    cdi = np.array([float_value(row, "CDi") for row in samples])
    feasible = np.array([row["feasible"].lower() == "true" for row in samples])

    fig, ax = plt.subplots(figsize=(6.8, 5.6), constrained_layout=True)
    scatter = ax.scatter(
        x[feasible],
        y[feasible],
        c=cdi[feasible],
        cmap="viridis_r",
        s=70,
        edgecolor="#111827",
        linewidth=0.35,
    )
    ax.scatter(
        x[~feasible],
        y[~feasible],
        c=cdi[~feasible],
        cmap="viridis_r",
        s=60,
        marker="x",
        linewidth=1.1,
    )
    ax.scatter(
        [4.159],
        [3.3272],
        marker="*",
        s=180,
        color="#F5C242",
        edgecolor="#111827",
        linewidth=0.8,
        label="Strict best",
        zorder=5,
    )
    fig.colorbar(scatter, ax=ax, label=r"$C_{D_i}$")
    ax.set_xlabel("Inboard-segment deflection [deg]")
    ax.set_ylabel("Outboard-segment deflection [deg]")
    ax.set_title("Two-segment conventional-control search")
    ax.grid(color="#E5E7EB", linewidth=0.7)
    ax.legend(frameon=False)
    save(fig, output, "02_corrected_hinged_deflection_space")


def interpolate_planform(loads: list[dict[str, str]], eta: np.ndarray):
    source_eta = np.array([float_value(row, "eta") for row in loads])
    source_y = np.array([float_value(row, "y_m") for row in loads])
    source_chord = np.array([float_value(row, "chord_m") for row in loads])
    y = np.interp(eta, source_eta, source_y)
    chord = np.interp(eta, source_eta, source_chord)
    leading = -0.25 * chord
    trailing = 0.75 * chord
    return y, leading, trailing, chord


def plot_authority_map(repo: Path, output: Path) -> None:
    loads = read_rows(
        repo
        / "argus_morphing/outputs/tyler_validation_2026_07_29"
        / "baseline_corrected/baseline_corrected_spanwise_loads.csv"
    )
    eta = np.linspace(0.0, 1.0, 300)
    y, leading, trailing, chord = interpolate_planform(loads, eta)

    fig, axes = plt.subplots(3, 1, figsize=(8.2, 7.5), constrained_layout=True)
    concepts = [
        ("Traditional hinged", 0.71, 0.97, 0.70, COLORS["hinged"]),
        ("Continuous trailing edge", 0.60, 1.00, 0.62, COLORS["camber"]),
        ("Distributed twist", 0.60, 1.00, 0.00, COLORS["twist"]),
    ]
    for ax, (title, eta0, eta1, xh, color) in zip(axes, concepts):
        ax.fill_between(y, leading, trailing, color="#E5E7EB", label="Fixed wing")
        mask = (eta >= eta0) & (eta <= eta1)
        active_leading = leading + xh * chord
        ax.fill_between(
            y[mask],
            active_leading[mask],
            trailing[mask],
            color=color,
            alpha=0.74,
            label="Commanded region",
        )
        ax.plot(y, leading, color="#1F2937", linewidth=1.2)
        ax.plot(y, trailing, color="#1F2937", linewidth=1.2)
        if title == "Distributed twist":
            axis_line = leading + 0.25 * chord
            ax.plot(
                y[mask],
                axis_line[mask],
                color="#111827",
                linestyle="--",
                linewidth=1.2,
                label="Rotation axis, x/c=0.25",
            )
        else:
            ax.plot(
                y[mask],
                active_leading[mask],
                color="#111827",
                linestyle="--",
                linewidth=1.2,
                label=f"Hinge/start, x/c={xh:.2f}",
            )
        ax.set_title(title)
        ax.set_xlabel("Semi-span y [m]")
        ax.set_ylabel("Chordwise coordinate [m]")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(color="#E5E7EB", linewidth=0.6)
        ax.legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.suptitle("Corrected low-speed comparison: geometric authority")
    save(fig, output, "03_corrected_concept_authority_map")


def plot_spanwise_loads(repo: Path, output: Path) -> None:
    paths = {
        "rigid": repo
        / "argus_morphing/outputs/tyler_validation_2026_07_29"
        / "baseline_corrected/baseline_corrected_spanwise_loads.csv",
        "hinged": repo
        / "argus_conventional_control_comparison/outputs"
        / "corrected_low_speed_validation/chc_g02_c17"
        / "chc_g02_c17_spanwise_loads.csv",
        "camber": repo
        / "argus_morphing/outputs/corrected_te_validation/cte_i002_c04"
        / "cte_i002_c04_spanwise_loads.csv",
        "twist": repo
        / "argus_twist_morphing/outputs"
        / "corrected_twist_validation/ctw_i001_c03"
        / "ctw_i001_c03_spanwise_loads.csv",
    }
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True, constrained_layout=True)
    for concept, path in paths.items():
        rows = read_rows(path)
        eta = [float_value(row, "eta") for row in rows]
        lift = [float_value(row, "lift_per_span_N_per_m") for row in rows]
        induced = [
            float_value(row, "induced_drag_per_span_N_per_m") for row in rows
        ]
        axes[0].plot(eta, lift, color=COLORS[concept], label=LABELS[concept], linewidth=1.8)
        axes[1].plot(
            eta, induced, color=COLORS[concept], label=LABELS[concept], linewidth=1.8
        )
    axes[0].set_ylabel("Lift per span [N/m]")
    axes[1].set_ylabel("Induced drag per span [N/m]")
    axes[1].set_xlabel(r"Semi-span coordinate $\eta$")
    axes[0].set_title("Strict matched spanwise loads at fixed lift")
    for ax in axes:
        ax.axvspan(0.60, 1.00, color="#D1FAE5", alpha=0.22)
        ax.grid(color="#E5E7EB", linewidth=0.7)
    axes[0].legend(frameon=False, ncol=2)
    save(fig, output, "04_corrected_four_concept_spanwise_loads")


def plot_performance(output: Path, summary: list[dict]) -> None:
    concepts = [row["concept"] for row in summary]
    labels = [LABELS[name].replace(" ", "\n") for name in concepts]
    colors = [COLORS[name] for name in concepts]
    reductions = [row["CDi_reduction_percent"] for row in summary]
    bending = [row["root_bending_increase_percent"] for row in summary]

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.8), constrained_layout=True)
    bars = axes[0].bar(labels, reductions, color=colors, edgecolor="#1F2937", linewidth=0.5)
    axes[0].bar_label(bars, labels=[f"{value:.2f}%" for value in reductions], padding=3)
    bars = axes[1].bar(labels, bending, color=colors, edgecolor="#1F2937", linewidth=0.5)
    axes[1].bar_label(bars, labels=[f"{value:.2f}%" for value in bending], padding=3)
    axes[1].axhline(6.8, color="#111827", linestyle="--", linewidth=1.2, label="6.8% screen")
    axes[0].set_ylabel(r"$C_{D_i}$ reduction from rigid baseline [%]")
    axes[1].set_ylabel("Half-wing root-bending increase [%]")
    axes[0].set_title("Aerodynamic benefit")
    axes[1].set_title("Load redistribution cost")
    for ax in axes:
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.7)
    axes[1].legend(frameon=False)
    fig.suptitle(r"Corrected strict comparison at $M=0.1$, fixed $C_L=0.428278$")
    save(fig, output, "05_corrected_four_concept_comparison")


def write_results(output: Path, summary: list[dict]) -> None:
    write_csv(output / "corrected_four_concept_comparison.csv", summary)
    payload = {
        "condition": {
            "mach": 0.1,
            "target_CL": 0.428277635108,
            "analysis": "wing-only VSPAERO, strict iterative trim",
            "baseline_geometry": "corrected inserted-airfoil interpolation",
        },
        "evidence": {
            "rigid_exact_cases": 1,
            "conventional_hinged_exact_search_cases": 49,
            "continuous_trailing_edge_exact_search_cases": 26,
            "distributed_twist_exact_search_cases": 26,
        },
        "results": summary,
        "interpretation": {
            "aerodynamic_ranking": [
                "continuous trailing edge",
                "distributed twist",
                "conventional hinged",
                "rigid baseline",
            ],
            "important_caveat": (
                "The conventional NASA aileron occupies eta 0.71-0.97 and x/c "
                "0.70-1.00, while both continuous concepts use eta 0.60-1.00. "
                "The comparison retains each concept's defined authority and is "
                "not an equal-area mechanism comparison."
            ),
        },
    }
    (output / "corrected_four_concept_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    hinged = next(row for row in summary if row["concept"] == "hinged")
    camber = next(row for row in summary if row["concept"] == "camber")
    twist = next(row for row in summary if row["concept"] == "twist")
    en = f"""# Corrected low-speed four-concept comparison

## Scope

All results use the corrected inserted-airfoil interpolation, wing-only
VSPAERO, Mach 0.1, and fixed CL = 0.428277635108. Final candidates were
rerun with iterative trim. The 6.8% root-bending increase is an illustrative
study screen, not a certified structural allowable.

## Strict results

| Concept | Case | CDi reduction | Drag-count reduction | Bending increase |
|---|---|---:|---:|---:|
| Rigid baseline | baseline_corrected | 0.000% | 0.000 | 0.000% |
| Conventional hinged | {hinged['case_id']} | {hinged['CDi_reduction_percent']:.3f}% | {hinged['CDi_reduction_drag_counts']:.3f} | {hinged['root_bending_increase_percent']:.3f}% |
| Continuous trailing edge | {camber['case_id']} | {camber['CDi_reduction_percent']:.3f}% | {camber['CDi_reduction_drag_counts']:.3f} | {camber['root_bending_increase_percent']:.3f}% |
| Distributed twist | {twist['case_id']} | {twist['CDi_reduction_percent']:.3f}% | {twist['CDi_reduction_drag_counts']:.3f} | {twist['root_bending_increase_percent']:.3f}% |

The aerodynamic ranking in this low-order model is continuous trailing-edge
camber, distributed twist, conventional hinged control, and rigid baseline.
The camber/twist difference is only
{camber['CDi_reduction_drag_counts'] - twist['CDi_reduction_drag_counts']:.3f}
drag counts, so it is not a sufficient basis for hardware down-selection.

## Fairness caveat

The conventional reference follows the NASA TP-1580 two-segment aileron:
eta 0.710-0.970 and x/c 0.70-1.00. The continuous concepts follow the ARGUS
outer-wing definition, eta 0.60-1.00. This preserves the real reference
geometry but gives the continuous concepts more spanwise authority. The
hinged model is also inviscid and zero-gap, so it does not include hinge-gap
or profile-drag penalties.
"""
    zh = f"""# 修正后的低速四方案对比

## 对比范围

所有结果均采用修正后的插入翼型插值、仅机翼 VSPAERO、马赫数 0.1 和
固定 CL = 0.428277635108。最终候选均进行了严格迭代配平。6.8% 的根部
弯矩增量只是研究用筛选线，不是经过结构认证的许用值。

## 严格结果

| 方案 | Case | CDi 降低 | 阻力 counts 降低 | 根部弯矩增加 |
|---|---|---:|---:|---:|
| 刚性基线 | baseline_corrected | 0.000% | 0.000 | 0.000% |
| 传统铰接式 | {hinged['case_id']} | {hinged['CDi_reduction_percent']:.3f}% | {hinged['CDi_reduction_drag_counts']:.3f} | {hinged['root_bending_increase_percent']:.3f}% |
| 连续后缘变弯度 | {camber['case_id']} | {camber['CDi_reduction_percent']:.3f}% | {camber['CDi_reduction_drag_counts']:.3f} | {camber['root_bending_increase_percent']:.3f}% |
| 分布式扭转 | {twist['case_id']} | {twist['CDi_reduction_percent']:.3f}% | {twist['CDi_reduction_drag_counts']:.3f} | {twist['root_bending_increase_percent']:.3f}% |

在当前低阶气动模型中，气动排序为：连续后缘变弯度、分布式扭转、
传统铰接式、刚性基线。后缘和扭转的差距只有
{camber['CDi_reduction_drag_counts'] - twist['CDi_reduction_drag_counts']:.3f}
个阻力 count，不能单独据此选择最终硬件方案。

## 公平性说明

传统方案保留 NASA TP-1580 的真实两段式副翼范围：
eta=0.710-0.970、x/c=0.70-1.00；两个连续变形方案采用 ARGUS 定义的
eta=0.60-1.00。因此这是“各自定义下的方案参考对比”，不是严格相同
变形面积的机构对比。传统铰接模型还是无黏、零缝隙模型，没有包含
铰链缝隙和型面阻力惩罚。
"""
    (output / "RESULTS_EN.md").write_text(en, encoding="utf-8")
    (output / "RESULTS_ZH.md").write_text(zh, encoding="utf-8")


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    repo = project.parent
    output = project / "plot" / "corrected_low_speed_comparison"
    summary = load_concepts(repo)

    assert all(row["strict_feasible"] for row in summary)
    cdi = {row["concept"]: row["CDi"] for row in summary}
    assert cdi["camber"] < cdi["twist"] < cdi["hinged"] < cdi["rigid"]

    plot_design_space(repo, output, summary)
    plot_deflection_space(repo, output)
    plot_authority_map(repo, output)
    plot_spanwise_loads(repo, output)
    plot_performance(output, summary)
    write_results(output, summary)
    print(f"Wrote corrected comparison package to {output}")


if __name__ == "__main__":
    main()

