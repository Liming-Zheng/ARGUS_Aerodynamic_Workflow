from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
CASE_ID = "ph2b_i001_c03"
BLUE = "#174A6B"
GREEN = "#4E8B57"
TEAL = "#237A72"
ORANGE = "#C56A32"
RED = "#B4473F"
PURPLE = "#785B9E"
LIGHT_GREEN = "#DDEADF"
GRAY = "#5B6670"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]):
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
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


def interpolate_schedule(schedule: list[dict], eta: np.ndarray, key: str) -> np.ndarray:
    source_eta = np.asarray([number(row, "eta") for row in schedule])
    source_value = np.asarray([number(row, key) for row in schedule])
    return np.interp(eta, source_eta, source_value)


def actuator_boundaries(count: int) -> np.ndarray:
    return np.linspace(0.60, 0.95, count + 1)


def actuator_stations(boundaries: np.ndarray) -> np.ndarray:
    return 0.5 * (boundaries[:-1] + boundaries[1:])


def build_station_table(loads: list[dict], schedule: list[dict]) -> list[dict]:
    eta = np.asarray([number(row, "eta") for row in loads])
    a_local = interpolate_schedule(schedule, eta, "A_local_over_c")
    te_m = interpolate_schedule(schedule, eta, "TE_displacement_m")
    outboard_torque = np.cumsum(
        (
            np.asarray([number(row, "hinge_moment_proxy_Nm_per_m") for row in loads])
            * np.asarray([number(row, "dy") for row in loads])
        )[::-1]
    )[::-1]
    rows = []
    for row, amp, te, torque in zip(loads, a_local, te_m, outboard_torque):
        rows.append({
            "eta": number(row, "eta"),
            "y_m": number(row, "y"),
            "dy_m": number(row, "dy"),
            "chord_m": number(row, "chord"),
            "A_local_over_c": amp,
            "TE_displacement_mm": 1000.0 * te,
            "lift_per_span_N_per_m": number(row, "lift_per_span_N_per_m"),
            "hinge_moment_proxy_Nm_per_m": number(row, "hinge_moment_proxy_Nm_per_m"),
            "outboard_integrated_torque_proxy_Nm": torque,
            "morph_region": str(row.get("morph_region", "")).lower() == "true",
        })
    return rows


def integrate_segment(rows: list[dict], eta_low: float, eta_high: float, station: float, actuator_id: str) -> dict:
    segment = [
        row for row in rows
        if eta_low <= number(row, "eta") < eta_high
    ]
    if not segment:
        return {
            "actuator_id": actuator_id,
            "eta_station": station,
            "eta_low": eta_low,
            "eta_high": eta_high,
        }
    dy = np.asarray([number(row, "dy_m") for row in segment])
    lift = np.asarray([number(row, "lift_per_span_N_per_m") for row in segment])
    torque_density = np.asarray([number(row, "hinge_moment_proxy_Nm_per_m") for row in segment])
    te = np.asarray([number(row, "TE_displacement_mm") for row in segment])
    amp = np.asarray([number(row, "A_local_over_c") for row in segment])
    chord = np.asarray([number(row, "chord_m") for row in segment])
    eta = np.asarray([number(row, "eta") for row in segment])
    return {
        "actuator_id": actuator_id,
        "eta_station": station,
        "eta_low": eta_low,
        "eta_high": eta_high,
        "span_fraction_width": eta_high - eta_low,
        "y_station_m": np.interp(station, eta, [number(row, "y_m") for row in segment]),
        "mean_chord_m": float(np.average(chord, weights=dy)),
        "mean_A_over_c": float(np.average(amp, weights=dy)),
        "max_A_over_c": float(np.max(amp)),
        "mean_TE_displacement_mm": float(np.average(te, weights=dy)),
        "max_abs_TE_displacement_mm": float(np.max(np.abs(te))),
        "segment_lift_N": float(np.sum(lift * dy)),
        "segment_hinge_torque_proxy_Nm": float(np.sum(torque_density * dy)),
        "peak_abs_hinge_moment_proxy_Nm_per_m": float(np.max(np.abs(torque_density))),
    }


def build_layouts(station_rows: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    all_rows = []
    by_layout = {}
    for count in [3, 4]:
        boundaries = actuator_boundaries(count)
        stations = actuator_stations(boundaries)
        layout_rows = []
        for index, (lo, hi, station) in enumerate(zip(boundaries[:-1], boundaries[1:], stations), start=1):
            row = integrate_segment(
                station_rows,
                float(lo),
                float(hi if index < count else hi + 1.0e-9),
                float(station),
                f"{count}A-{index}",
            )
            row["layout"] = f"{count}_actuator"
            layout_rows.append(row)
            all_rows.append(row)
        by_layout[f"{count}_actuator"] = layout_rows
    return all_rows, by_layout


def plot_station_data(output: Path, station_rows: list[dict], by_layout: dict[str, list[dict]]):
    eta = np.asarray([number(row, "eta") for row in station_rows])
    te = np.asarray([number(row, "TE_displacement_mm") for row in station_rows])
    lift = np.asarray([number(row, "lift_per_span_N_per_m") for row in station_rows])
    torque_density = np.asarray([number(row, "hinge_moment_proxy_Nm_per_m") for row in station_rows])
    outboard_torque = np.asarray([number(row, "outboard_integrated_torque_proxy_Nm") for row in station_rows])

    fig, axes = plt.subplots(4, 1, figsize=(10.0, 11.5), sharex=True, constrained_layout=True)
    series = [
        (te, "TE displacement [mm]", GREEN),
        (lift, "Lift per span [N/m]", BLUE),
        (torque_density, "Hinge moment proxy [N m/m]", ORANGE),
        (outboard_torque, "Outboard integrated torque [N m]", PURPLE),
    ]
    for ax, (values, ylabel, color) in zip(axes, series):
        ax.plot(eta, values, color=color, lw=2.2)
        ax.axvspan(0.60, 0.95, color=LIGHT_GREEN, alpha=0.55)
        for row in by_layout["4_actuator"]:
            ax.axvline(number(row, "eta_station"), color=GRAY, lw=0.9, ls=":")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.24)
    axes[0].set_title("Actuator-relevant spanwise quantities, ph2b_i001_c03")
    axes[-1].set_xlabel("eta = y/(b/2)")
    save(fig, output, "actuator_relevant_spanwise_quantities")

    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.8), constrained_layout=True)
    for ax, layout_name in zip(axes, ["3_actuator", "4_actuator"]):
        rows = by_layout[layout_name]
        labels = [row["actuator_id"] for row in rows]
        x = np.arange(len(rows))
        torque = [abs(number(row, "segment_hinge_torque_proxy_Nm")) for row in rows]
        stroke = [number(row, "max_abs_TE_displacement_mm") for row in rows]
        ax2 = ax.twinx()
        bars = ax.bar(x - 0.18, torque, width=0.36, color=ORANGE, label="|Segment torque|")
        ax2.bar(x + 0.18, stroke, width=0.36, color=GREEN, label="Max stroke")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel("|Segment torque proxy| [N m]", color=ORANGE)
        ax2.set_ylabel("Max |TE displacement| [mm]", color=GREEN)
        ax.set_title(layout_name.replace("_", " "))
        ax.grid(axis="y", alpha=0.22)
        ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=8)
    fig.suptitle("Actuator segment torque and stroke comparison")
    save(fig, output, "actuator_layout_segment_comparison")

    fig, ax = plt.subplots(figsize=(10.0, 5.4), constrained_layout=True)
    ax.plot(eta, te, color=GREEN, lw=2.3, label="TE displacement")
    colors = {"3_actuator": ORANGE, "4_actuator": BLUE}
    for layout_name, rows in by_layout.items():
        for row in rows:
            ax.axvline(number(row, "eta_station"), color=colors[layout_name], ls="--", lw=1.2, alpha=0.8)
            ax.text(
                number(row, "eta_station"),
                min(te) * 0.92,
                row["actuator_id"],
                rotation=90,
                va="bottom",
                ha="center",
                fontsize=8,
                color=colors[layout_name],
            )
    ax.axvspan(0.60, 0.95, color=LIGHT_GREEN, alpha=0.45)
    ax.set_xlabel("eta = y/(b/2)")
    ax.set_ylabel("TE displacement [mm]")
    ax.set_title("Candidate actuator stationing over trailing-edge displacement")
    ax.grid(alpha=0.24)
    save(fig, output, "actuator_stationing_overlay")


def markdown_table(rows: list[dict]) -> str:
    cols = [
        "actuator_id",
        "eta_station",
        "eta_low",
        "eta_high",
        "mean_TE_displacement_mm",
        "max_abs_TE_displacement_mm",
        "segment_lift_N",
        "segment_hinge_torque_proxy_Nm",
    ]
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for row in rows:
        line = []
        for col in cols:
            value = row.get(col, "")
            if isinstance(value, float):
                value = f"{value:.3f}"
            line.append(str(value))
        lines.append("| " + " | ".join(line) + " |")
    return "\n".join(lines)


def write_reports(output: Path, all_layout_rows: list[dict], by_layout: dict[str, list[dict]]):
    cn = f"""# Preliminary actuator sizing package

Candidate: `{CASE_ID}`.

这里的结果是执行器前期 sizing 的概念级输入，不是最终结构额定载荷。
`hinge torque proxy` 来自 VSPAERO sectional moment proxy，尚未包括结构刚度、
传力路径、摩擦、机构效率和安全系数。

## 3-actuator layout

{markdown_table(by_layout['3_actuator'])}

## 4-actuator layout

{markdown_table(by_layout['4_actuator'])}

建议解释：

- 3-actuator layout 更简单，但单个 actuator 负责的 span segment 更宽；
- 4-actuator layout 分担更细，单段 torque proxy 和 stroke 分布更容易管理；
- 当前最大 TE displacement 大约 20 mm 量级；
- segment torque proxy 是气动代理值，后续需要结构模型换算成实际 actuator load。
"""
    en = f"""# Preliminary actuator sizing package

Candidate: `{CASE_ID}`.

These values are conceptual actuator-sizing inputs. The hinge torque proxy is
derived from VSPAERO sectional moments and does not include structural
stiffness, load paths, friction, mechanism efficiency, or safety factors.

## 3-actuator layout

{markdown_table(by_layout['3_actuator'])}

## 4-actuator layout

{markdown_table(by_layout['4_actuator'])}

Interpretation:

- the 3-actuator layout is simpler but each actuator covers a wider spanwise segment;
- the 4-actuator layout distributes the morphing region into smaller segments;
- the peak trailing-edge displacement is on the order of 20 mm;
- segment torque proxy should be converted into real actuator load using a structural/mechanism model.
"""
    latex = r"""\section{Preliminary actuator implications}

The preferred aerodynamic candidate can also be post-processed into quantities
that are more directly useful for actuator discussions. The current quantities
are still conceptual: the hinge-moment value is an aerodynamic proxy from
VSPAERO sectional moments and does not include structural stiffness, load path,
mechanism efficiency, friction, or safety factors.

\begin{figure}[H]
    \centering
    \includegraphics[width=0.92\linewidth]{actuator_relevant_spanwise_quantities.png}
    \caption{Actuator-relevant spanwise quantities for the preferred phase-2
    candidate. Vertical dotted lines indicate the four-actuator stationing
    concept.}
    \label{fig:actuator-spanwise}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=0.9\linewidth]{actuator_layout_segment_comparison.png}
    \caption{Comparison of 3-actuator and 4-actuator segment loads and maximum
    trailing-edge stroke.}
    \label{fig:actuator-layout-comparison}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=0.86\linewidth]{actuator_stationing_overlay.png}
    \caption{Candidate actuator stationing overlaid on the trailing-edge
    displacement schedule.}
    \label{fig:actuator-stationing}
\end{figure}

The 3-actuator layout is mechanically simpler, but each actuator covers a wider
spanwise segment. The 4-actuator layout distributes the morphing region into
smaller segments and may be more suitable if local skin deformation or load
sharing becomes a concern. At this stage, these layouts should be treated as
discussion inputs for the actuator team rather than finalized mechanism
requirements.
"""
    (output / "actuator_sizing_package_CN.md").write_text(cn, encoding="utf-8")
    (output / "actuator_sizing_package_EN.md").write_text(en, encoding="utf-8")
    (output / "actuator_implications_report_section.tex").write_text(latex, encoding="utf-8")


def main():
    case_dir = PROJECT / "outputs" / "final_design_package" / CASE_ID
    output = PROJECT / "outputs" / "actuator_sizing" / CASE_ID
    output.mkdir(parents=True, exist_ok=True)
    loads = read_csv(case_dir / f"{CASE_ID}_spanwise_loads.csv")
    schedule = read_csv(case_dir / f"{CASE_ID}_section_schedule.csv")
    station_rows = build_station_table(loads, schedule)
    layout_rows, by_layout = build_layouts(station_rows)
    write_csv(output / f"{CASE_ID}_actuator_station_loads.csv", station_rows)
    write_csv(output / f"{CASE_ID}_actuator_layout_segments.csv", layout_rows)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })
    plot_station_data(output, station_rows, by_layout)
    write_reports(output, layout_rows, by_layout)
    print(f"Wrote actuator sizing package to {output}")


if __name__ == "__main__":
    main()

