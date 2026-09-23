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
TEAL = "#237A72"
ORANGE = "#C56A32"
RED = "#B4473F"
PURPLE = "#785B9E"
GRAY = "#5B6670"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]):
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def number(row: dict, key: str, default=0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def save(fig, out: Path, name: str):
    fig.savefig(out / f"{name}.png", dpi=240, bbox_inches="tight")
    fig.savefig(out / f"{name}.svg", bbox_inches="tight")
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def equivalent_flap_angle(xh: float, amplitude: float) -> float:
    return float(np.degrees(np.arctan2(amplitude, 1.0 - xh)))


def xh_sensitivity(output: Path) -> list[dict]:
    exact = read_csv(PROJECT / "outputs" / "exact_trim_loads" / "exact_trim_load_summary.csv")
    rows = [
        row for row in exact
        if row["case_id"] != "refined_baseline"
        and row["shape_type"] == "uniform"
        and abs(number(row, "A_max_over_c") - 0.04) < 1e-8
    ]
    rows = sorted(rows, key=lambda row: number(row, "x_h_over_c"))
    table = []
    for row in rows:
        xh = number(row, "x_h_over_c")
        amp = number(row, "A_max_over_c")
        table.append({
            "case_id": row["case_id"],
            "x_h_over_c": f"{xh:.2f}",
            "A_over_c": f"{amp:.3f}",
            "equivalent_flap_angle_deg": f"{equivalent_flap_angle(xh, amp):.3f}",
            "CDi": f"{number(row, 'CDi'):.9f}",
            "CDi_reduction_percent": f"{-number(row, 'CDi_change_percent_vs_baseline'):.3f}",
            "root_bending_increase_percent": f"{number(row, 'root_bending_change_percent_vs_baseline'):.3f}",
            "hinge_torque_proxy_Nm": f"{number(row, 'morph_region_hinge_torque_proxy_Nm'):.1f}",
        })
    write_csv(output / "xh_sensitivity_uniform_A004.csv", table)

    xh = np.asarray([number(row, "x_h_over_c") for row in rows])
    cdi_red = np.asarray([-number(row, "CDi_change_percent_vs_baseline") for row in rows])
    bending = np.asarray([number(row, "root_bending_change_percent_vs_baseline") for row in rows])
    torque = np.asarray([abs(number(row, "morph_region_hinge_torque_proxy_Nm")) for row in rows])
    flap = np.asarray([equivalent_flap_angle(number(row, "x_h_over_c"), number(row, "A_max_over_c")) for row in rows])

    fig, axes = plt.subplots(2, 2, figsize=(11, 8.0), constrained_layout=True)
    series = [
        (cdi_red, "CDi reduction [%]", GREEN),
        (bending, "Root bending increase [%]", ORANGE),
        (torque, "|Torque proxy| [N m]", RED),
        (flap, "Equivalent rigid-flap angle [deg]", PURPLE),
    ]
    for ax, (values, ylabel, color) in zip(axes.ravel(), series):
        ax.plot(xh, values, marker="o", lw=2.2, color=color)
        ax.set_xlabel("Morphing start line, x_h/c")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
    fig.suptitle("Chordwise morphing-start sensitivity, uniform A/c=0.04")
    save(fig, output, "xh_sensitivity_uniform_A004")
    return table


def values_from_row(row: dict) -> np.ndarray:
    return np.asarray([number(row, f"A{i}_over_c") for i in range(1, 6)])


def curvature(values: np.ndarray) -> float:
    if values.size < 3:
        return 0.0
    return float(np.sum(np.diff(values, n=2) ** 2))


def objective_study(output: Path) -> list[dict]:
    samples = read_csv(PROJECT / "outputs" / "optimization" / "optimization_samples.csv")
    strict = {}
    for case_id in ["usr_i003_c03", "ph2b_i001_c03", "opt_s002"]:
        path = PROJECT / "outputs" / "final_design_package" / case_id / f"{case_id}_optimization_result.csv"
        if path.exists():
            strict[case_id] = read_csv(path)[0]
    baseline = next(
        row for row in read_csv(PROJECT / "outputs" / "exact_trim_loads" / "exact_trim_load_summary.csv")
        if row["case_id"] == "refined_baseline"
    )
    baseline_cdi = number(baseline, "CDi")

    # Use strict values where available; otherwise use optimization-stage values.
    rows_by_case = {row["case_id"]: row for row in samples}
    rows_by_case.update(strict)
    rows = list(rows_by_case.values())
    feasible = [
        row for row in rows
        if number(row, "root_bending_increase_percent", 1e9) <= 6.8
        and abs(number(row, "hinge_torque_proxy_Nm", 1e9)) <= 1050.0
        and number(row, "max_adjacent_delta", 1e9) <= 0.018
    ]

    def score_cdi(row):
        return number(row, "CDi")

    def score_torque(row):
        return abs(number(row, "hinge_torque_proxy_Nm"))

    def score_bending(row):
        return number(row, "root_bending_increase_percent")

    def score_smooth(row):
        vals = values_from_row(row)
        return vals[0] ** 2 + vals[-1] ** 2 + 4.0 * curvature(vals)

    def score_balanced(row):
        vals = values_from_row(row)
        return (
            number(row, "CDi")
            + 0.03 * max(0.0, number(row, "root_bending_increase_percent")) / 1000.0
            + 0.01 * abs(number(row, "hinge_torque_proxy_Nm")) / 1.0e6
            + 0.06 * (vals[0] ** 2 + vals[-1] ** 2)
            + 0.18 * curvature(vals)
        )

    objectives = [
        ("min_CDi", "Minimum induced drag", score_cdi),
        ("min_torque_proxy", "Minimum actuator torque proxy", score_torque),
        ("min_root_bending", "Minimum root bending increase", score_bending),
        ("smoothest_shape", "Smoothest morphing schedule", score_smooth),
        ("balanced_phase2", "Balanced aerodynamic/structural/smoothness", score_balanced),
    ]
    table = []
    for objective_id, label, score in objectives:
        row = min(feasible, key=score)
        cdi = number(row, "CDi")
        vals = values_from_row(row)
        table.append({
            "objective_id": objective_id,
            "objective_meaning": label,
            "selected_case": row["case_id"],
            "CDi": f"{cdi:.9f}",
            "CDi_reduction_percent": f"{100.0 * (baseline_cdi - cdi) / baseline_cdi:.3f}",
            "root_bending_increase_percent": f"{number(row, 'root_bending_increase_percent'):.3f}",
            "hinge_torque_proxy_Nm": f"{number(row, 'hinge_torque_proxy_Nm'):.1f}",
            "max_adjacent_delta": f"{number(row, 'max_adjacent_delta'):.5f}",
            "A1_over_c": f"{vals[0]:.5f}",
            "Amax_over_c": f"{np.max(vals):.5f}",
        })
    write_csv(output / "alternative_objective_selected_cases.csv", table)

    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    colors = [GREEN, RED, ORANGE, PURPLE, BLUE]
    x = np.arange(len(table))
    cdi_reduction = [number(row, "CDi_reduction_percent") for row in table]
    bending = [number(row, "root_bending_increase_percent") for row in table]
    width = 0.36
    ax.bar(x - width / 2, cdi_reduction, width, label="CDi reduction [%]", color=GREEN)
    ax.bar(x + width / 2, bending, width, label="Root bending increase [%]", color=ORANGE)
    ax.set_xticks(x)
    ax.set_xticklabels([row["objective_id"].replace("_", "\n") for row in table], fontsize=8)
    ax.set_ylabel("Percent")
    ax.set_title("Selected candidate changes under different objective definitions")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    save(fig, output, "alternative_objective_tradeoff")
    return table


def markdown_table(rows: list[dict]) -> str:
    columns = list(rows[0])
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[col]) for col in columns) + " |")
    return "\n".join(lines)


def write_reports(output: Path, xh_rows: list[dict], objective_rows: list[dict]):
    cn = f"""# Chordwise Start-Line and Objective Sensitivity Study

## x_h/c 为什么重要？

`x_h/c` 是弦向变形开始的位置。它不是最终结构铰链定义，而是当前气动模型中
“从哪里开始改变 camber”的参数。对同一个 trailing-edge 位移 `A/c`：

- `x_h/c` 越靠前，参与变形的弦长越长，变形更分散，但会影响更大的翼型区域；
- `x_h/c` 越靠后，变形区域更短，同样 trailing-edge 位移对应更大的等效 flap 角；
- 因此它会同时影响 CDi、俯仰力矩、root bending 和 hinge torque proxy。

当前使用 `0.62` 不是因为它已经被证明为结构最优，而是因为它代表比较靠后的
连续 trailing-edge morphing 区域。它比 `0.50` 更接近传统 flap/aileron 后缘区域，
同时比更靠后的铰线保留更多连续变形长度。对结构组来说，这个参数应该继续作为
actuator layout 的关键设计变量。

## Uniform A/c=0.04 的已有严格 DOE 对比

{markdown_table(xh_rows)}

## 其他优化目标能怎么选？

当前框架已经支持通过配置文件改变目标函数。可以选择：

- 最小 `CDi`：气动效率最强，但容易逼近结构限制；
- 最小 hinge torque proxy：更偏 actuator sizing；
- 最小 root bending：更偏结构安全裕度；
- 最平滑形状：更偏连续 morphing 皮肤和机构可实现性；
- balanced objective：在 CDi、root bending、torque 和平滑性之间折中。

## 当前样本池在不同目标下选出的候选

{markdown_table(objective_rows)}

建议报告中强调：现在不是只能给出一个最优解，而是已经有一套框架可以按不同
利益相关方的关注点重新定义“最优”。这对和结构/执行器团队讨论非常重要。
"""
    en = f"""# Chordwise Start-Line and Objective Sensitivity Study

## Why x_h/c matters

`x_h/c` defines where the continuous camber morphing starts in the chordwise
direction. It is not yet a final structural hinge line. For the same
trailing-edge displacement `A/c`:

- a forward start line spreads the deformation over a longer chord;
- an aft start line gives a shorter deformable chord and a larger equivalent
rigid-flap angle;
- the selected value therefore changes induced drag, pitching moment, root
bending, and hinge-moment proxy.

The current value `x_h/c=0.62` should be interpreted as a plausible
trailing-edge morphing start line, not as a proven structural optimum. It is a
key variable for the actuator team.

## Existing strict DOE comparison for uniform A/c=0.04

{markdown_table(xh_rows)}

## Alternative objective definitions

The same framework can be redirected toward different definitions of optimum:

- minimum `CDi` for aerodynamic efficiency;
- minimum hinge torque proxy for actuator sizing;
- minimum root bending for structural margin;
- smoothest shape for continuous-skin feasibility;
- balanced objective for the current aerodynamic/structural compromise.

## Selected candidates under different objectives

{markdown_table(objective_rows)}
"""
    latex_rows = []
    for row in objective_rows:
        case_tex = row["selected_case"].replace("_", r"\_")
        objective_tex = row["objective_id"].replace("_", " ")
        latex_rows.append(
            f"{objective_tex} & \\texttt{{{case_tex}}} & "
            f"{row['CDi_reduction_percent']} & {row['root_bending_increase_percent']} & "
            f"{row['hinge_torque_proxy_Nm']} & {row['max_adjacent_delta']} \\\\"
        )

    latex = r"""\section{Chordwise start-line and objective sensitivity}

\subsection{Effect of chordwise morphing start line}

The parameter \(x_h/c\) controls where the continuous camber morphing starts in
the chordwise direction. It should not yet be interpreted as a final structural
hinge line; rather, it is the aerodynamic representation of the start of the
deformable trailing-edge region. For the same trailing-edge displacement, a
forward start line spreads the deformation over a longer chord, whereas an aft
start line creates a shorter deformable chord and a larger equivalent
rigid-flap angle. This affects induced drag, pitching moment, root bending, and
the hinge-moment proxy.

The current value \(x_h/c=0.62\) is therefore a design assumption. It represents
a plausible trailing-edge morphing region, but it should remain open for
discussion with the structural and actuator teams.

\begin{figure}[H]
    \centering
    \includegraphics[width=0.88\linewidth]{xh_sensitivity_uniform_A004.png}
    \caption{Sensitivity of aerodynamic and load metrics to the chordwise
    morphing start line for a uniform \(A/c=0.04\) deformation.}
    \label{fig:xh-sensitivity}
\end{figure}

\subsection{Alternative optimization objectives}

The current framework can be redirected toward different engineering goals.
Instead of only minimizing \(C_{D_i}\), the optimizer can minimize actuator
torque proxy, root-bending increase, spanwise shape roughness, or a balanced
weighted objective. This is important because the definition of ``best'' depends
on whether the stakeholder is focused on aerodynamics, structures, or actuator
sizing.

\begin{figure}[H]
    \centering
    \includegraphics[width=0.88\linewidth]{alternative_objective_tradeoff.png}
    \caption{Different objective definitions select different candidates from
    the current exact sample pool.}
    \label{fig:alternative-objectives}
\end{figure}

\begin{table}[H]
\centering
\small
\begin{tabular}{llrrrr}
\toprule
Objective & Selected case & \(C_{D_i}\) red. [\%] & Root bend [\%] & Torque [N\,m] & Max \(\Delta A/c\) \\
\midrule
""" + "\n".join(latex_rows) + r"""
\bottomrule
\end{tabular}
\caption{Candidates selected from the current sample pool under different
objective definitions.}
\label{tab:alternative-objectives}
\end{table}
"""
    (output / "chordwise_start_and_objective_study_CN.md").write_text(cn, encoding="utf-8")
    (output / "chordwise_start_and_objective_study_EN.md").write_text(en, encoding="utf-8")
    (output / "chordwise_start_and_objective_study.tex").write_text(latex, encoding="utf-8")


def main():
    output = PROJECT / "outputs" / "sensitivity_objective_study"
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })
    xh_rows = xh_sensitivity(output)
    objective_rows = objective_study(output)
    write_reports(output, xh_rows, objective_rows)
    print(f"Wrote sensitivity/objective study to {output}")


if __name__ == "__main__":
    main()

