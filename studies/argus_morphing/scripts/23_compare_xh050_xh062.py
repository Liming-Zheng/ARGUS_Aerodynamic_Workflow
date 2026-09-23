from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
CASES = {
    "xh050b_i001_c03": "x_h/c=0.50 balanced",
    "ph2b_i001_c03": "x_h/c=0.62 balanced",
}
COLORS = {
    "xh050b_i001_c03": "#237A72",
    "ph2b_i001_c03": "#4E8B57",
}
BLUE = "#174A6B"
ORANGE = "#C56A32"
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


def save(fig, output: Path, name: str):
    fig.savefig(output / f"{name}.png", dpi=240, bbox_inches="tight")
    fig.savefig(output / f"{name}.svg", bbox_inches="tight")
    fig.savefig(output / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def result(case_id: str) -> dict:
    return read_csv(
        PROJECT / "outputs" / "final_design_package" / case_id / f"{case_id}_optimization_result.csv"
    )[0]


def schedule(case_id: str) -> list[dict]:
    return read_csv(
        PROJECT / "outputs" / "final_design_package" / case_id / f"{case_id}_section_schedule.csv"
    )


def equivalent_angle(xh: float, amp: float) -> float:
    return float(np.degrees(np.arctan2(amp, 1.0 - xh)))


def make_table(output: Path) -> list[dict]:
    baseline = next(
        row for row in read_csv(PROJECT / "outputs" / "exact_trim_loads" / "exact_trim_load_summary.csv")
        if row["case_id"] == "refined_baseline"
    )
    baseline_cdi = number(baseline, "CDi")
    rows = []
    for case_id, label in CASES.items():
        row = result(case_id)
        sched = schedule(case_id)
        morph = [item for item in sched if str(item.get("morphed", "")).lower() == "true"]
        max_amp = max(number(item, "A_local_over_c") for item in morph)
        xh = number(morph[0], "x_h_over_c")
        rows.append({
            "case_id": case_id,
            "label": label,
            "x_h_over_c": f"{xh:.2f}",
            "CDi": f"{number(row, 'CDi'):.9f}",
            "CDi_reduction_percent": f"{100.0 * (baseline_cdi - number(row, 'CDi')) / baseline_cdi:.3f}",
            "root_bending_increase_percent": f"{number(row, 'root_bending_increase_percent'):.3f}",
            "hinge_torque_proxy_Nm": f"{number(row, 'hinge_torque_proxy_Nm'):.1f}",
            "max_adjacent_delta": f"{number(row, 'max_adjacent_delta'):.5f}",
            "Amax_over_c": f"{max_amp:.5f}",
            "equivalent_angle_at_Amax_deg": f"{equivalent_angle(xh, max_amp):.3f}",
            "strict_feasible": row["feasible"],
        })
    write_csv(output / "xh050_vs_xh062_strict_comparison.csv", rows)
    return rows


def plot_comparison(output: Path, table: list[dict]):
    labels = [row["x_h_over_c"] for row in table]
    x = np.arange(len(table))
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.5), constrained_layout=True)
    metrics = [
        ("CDi_reduction_percent", "CDi reduction [%]", "#4E8B57"),
        ("root_bending_increase_percent", "Root bending increase [%]", "#C56A32"),
        ("hinge_torque_proxy_Nm", "Torque proxy [N m]", "#B4473F"),
        ("equivalent_angle_at_Amax_deg", "Eq. flap angle at Amax [deg]", "#785B9E"),
    ]
    for ax, (key, ylabel, color) in zip(axes.ravel(), metrics):
        values = [number(row, key) for row in table]
        bars = ax.bar(labels, values, color=color, alpha=0.9)
        ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
        ax.set_xlabel("x_h/c")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.24)
    fig.suptitle("Strict comparison of balanced candidates at x_h/c=0.50 and 0.62", fontsize=15, weight="bold")
    save(fig, output, "xh050_vs_xh062_metric_comparison")

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 7.0), sharex=True, constrained_layout=True)
    for case_id, label in CASES.items():
        rows = schedule(case_id)
        eta = [number(row, "eta") for row in rows]
        amp = [number(row, "A_local_over_c") for row in rows]
        te = [1000.0 * number(row, "TE_displacement_m") for row in rows]
        axes[0].plot(eta, amp, color=COLORS[case_id], lw=2.2, marker="o", ms=3, label=label)
        axes[1].plot(eta, te, color=COLORS[case_id], lw=2.2, marker="s", ms=3, label=label)
    for ax in axes:
        ax.axvspan(0.60, 0.95, color="#DDEADF", alpha=0.55)
        ax.grid(alpha=0.24)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("A(eta)/c")
    axes[0].set_title("Spanwise morphing schedules")
    axes[1].set_ylabel("TE displacement [mm]")
    axes[1].set_xlabel("eta = y/(b/2)")
    save(fig, output, "xh050_vs_xh062_schedule_overlay")


def markdown_table(rows: list[dict]) -> str:
    cols = list(rows[0])
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[col]) for col in cols) + " |")
    return "\n".join(lines)


def write_reports(output: Path, rows: list[dict]):
    table = markdown_table(rows)
    en = f"""# x_h/c = 0.50 versus 0.62 balanced comparison

Both candidates were strictly validated with iterative fixed-CL VSPAERO.

{table}

The `x_h/c=0.50` candidate has lower root bending than the current `0.62`
balanced candidate, but also less induced-drag reduction. This suggests that a
more forward morphing start line can be structurally attractive, while the aft
start line remains more effective for the current aerodynamic benefit target.

The comparison should be presented as a sensitivity result, not as a final
decision. The structural team can use it to decide whether the additional
deformable chord required by `x_h/c=0.50` is realistic.
"""
    cn = f"""# x_h/c = 0.50 与 0.62 的 balanced 候选对比

两个候选都已经使用 iterative fixed-CL VSPAERO 严格复算。

{table}

`x_h/c=0.50` 候选的根弯矩更低，但诱导阻力降低也更少。这说明更靠前的
变形起始线可能对结构载荷更友好，但在当前目标下，靠后的 `0.62` 起始线
保留了更明显的气动收益。

这个结果应该作为 sensitivity，而不是最终结论。结构/执行器团队需要判断
`x_h/c=0.50` 所需的更长可变形弦长是否现实。
"""
    latex = r"""\subsection{Balanced comparison of \(x_h/c=0.50\) and \(x_h/c=0.62\)}

To further study the chordwise morphing start line, a balanced optimization was
also run with \(x_h/c=0.50\). The resulting candidate was strictly validated and
compared with the current \(x_h/c=0.62\) balanced candidate.

\begin{figure}[H]
    \centering
    \includegraphics[width=0.9\linewidth]{xh050_vs_xh062_metric_comparison.png}
    \caption{Strict metric comparison between balanced candidates at
    \(x_h/c=0.50\) and \(x_h/c=0.62\).}
    \label{fig:xh050-xh062-metrics}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=0.86\linewidth]{xh050_vs_xh062_schedule_overlay.png}
    \caption{Spanwise morphing schedule comparison for the \(x_h/c=0.50\) and
    \(x_h/c=0.62\) balanced candidates.}
    \label{fig:xh050-xh062-schedules}
\end{figure}

The \(x_h/c=0.50\) candidate has lower root bending, but also less induced-drag
reduction than the \(x_h/c=0.62\) balanced candidate. This suggests that moving
the morphing start line forward may be structurally attractive, but its benefit
depends on whether the longer deformable chord is realistic for the actuator
and skin design.
"""
    (output / "xh050_vs_xh062_comparison_EN.md").write_text(en, encoding="utf-8")
    (output / "xh050_vs_xh062_comparison_CN.md").write_text(cn, encoding="utf-8")
    (output / "xh050_vs_xh062_report_section.tex").write_text(latex, encoding="utf-8")


def main():
    output = PROJECT / "outputs" / "xh_start_comparison"
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })
    table = make_table(output)
    plot_comparison(output, table)
    write_reports(output, table)
    print(f"Wrote x_h/c comparison to {output}")


if __name__ == "__main__":
    main()

