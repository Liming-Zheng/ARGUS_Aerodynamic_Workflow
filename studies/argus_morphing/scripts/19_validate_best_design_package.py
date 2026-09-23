from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")
DEFAULT_PYTHON = Path(r"<OPENVSP_PYTHON>")

sys.path.insert(0, str(PROJECT / "src"))
from argus_morphing.airfoil_io import (  # noqa: E402
    cosine_grid,
    interpolate_surfaces,
    read_openvsp_airfoil_csv,
)
from argus_morphing.airfoil_morphing import morph_airfoil  # noqa: E402


BLUE = "#174A6B"
GREEN = "#4E8B57"
TEAL = "#237A72"
ORANGE = "#C56A32"
RED = "#B4473F"
PURPLE = "#785B9E"
GRAY = "#5B6670"
LIGHT_GREEN = "#DDEADF"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Strictly validate the current best ARGUS morphing design and build a presentation-ready package."
    )
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--case-id", default=None, help="Default: case_id in current_best_design.json")
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--cl-tolerance", type=float, default=2.0e-5)
    parser.add_argument("--skip-vspaero", action="store_true", help="Only rebuild plots/reports from existing strict results.")
    return parser.parse_args()


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


def number(row: dict, name: str, default=0.0) -> float:
    try:
        return float(row.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def as_percent(value: float) -> str:
    return f"{value:.3f}%"


def save_figure(fig, output: Path, name: str):
    fig.savefig(output / f"{name}.svg", bbox_inches="tight")
    fig.savefig(output / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(output / f"{name}.png", dpi=240, bbox_inches="tight")
    plt.close(fig)


def current_best_case(project: Path) -> str:
    path = project / "outputs" / "optimization" / "user_optimization" / "current_best_design.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data["case_id"])


def prepare_case(project: Path, case_id: str) -> Path:
    source = project / "outputs" / "optimization" / "samples" / case_id
    if not source.exists():
        raise FileNotFoundError(source)
    output = project / "outputs" / "final_design_package" / case_id
    output.mkdir(parents=True, exist_ok=True)

    for suffix in [".vsp3", "_design.json", "_section_schedule.csv"]:
        src = source / f"{case_id}{suffix}"
        if src.exists():
            shutil.copy2(src, output / src.name)

    fast_result = source / f"{case_id}_optimization_result.csv"
    if fast_result.exists():
        shutil.copy2(fast_result, output / f"{case_id}_fast_search_result.csv")
    return output


def run_strict_validation(args, case_dir: Path):
    script = args.project / "scripts" / "15_run_optimization_samples.py"
    command = [
        str(args.python),
        str(script),
        "--worker",
        "--project",
        str(args.project),
        "--openvsp-root",
        str(args.openvsp_root),
        "--case-dir",
        str(case_dir),
        "--trim-mode",
        "iterative",
        "--cl-tolerance",
        str(args.cl_tolerance),
        "--force",
    ]
    completed = subprocess.run(
        command,
        cwd=case_dir,
        capture_output=True,
        text=True,
    )
    log_path = case_dir / f"{case_dir.name}_strict_validation.log"
    log_path.write_text(
        completed.stdout + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(f"Strict validation failed. See {log_path}")


def plot_schedule(case_id: str, schedule: list[dict], output: Path):
    eta = np.asarray([number(row, "eta") for row in schedule])
    amp = np.asarray([number(row, "A_local_over_c") for row in schedule])
    te_m = np.asarray([number(row, "TE_displacement_m") for row in schedule])
    morphed = np.asarray([str(row.get("morphed", "")).lower() == "true" for row in schedule])

    fig, axes = plt.subplots(2, 1, figsize=(9.5, 7.0), sharex=True, constrained_layout=True)
    axes[0].plot(eta, amp, color=GREEN, marker="o", lw=2.2, ms=4)
    axes[1].plot(eta, 1000.0 * te_m, color=ORANGE, marker="s", lw=2.2, ms=4)
    for ax in axes:
        ax.axvspan(0.60, 0.95, color=LIGHT_GREEN, alpha=0.65)
        ax.grid(alpha=0.24)
    axes[0].scatter(eta[morphed], amp[morphed], color=GREEN, s=36, zorder=3)
    axes[0].set_ylabel("Local morphing amplitude A/c")
    axes[0].set_title(f"{case_id}: spanwise morphing schedule")
    axes[1].set_xlabel("eta = y/(b/2)")
    axes[1].set_ylabel("Trailing-edge displacement [mm]")
    save_figure(fig, output, "01_strict_best_spanwise_schedule")


def plot_airfoil_sections(project: Path, case_id: str, schedule: list[dict], output: Path):
    raw = project / "outputs" / "baseline" / "raw" / "baseline_airfoil_points.csv"
    upper, lower = read_openvsp_airfoil_csv(raw, 4)
    x = cosine_grid(241)
    upper_z, lower_z = interpolate_surfaces(upper, lower, x)
    morphed_rows = [row for row in schedule if str(row.get("morphed", "")).lower() == "true"]
    selected = [
        morphed_rows[0],
        max(morphed_rows, key=lambda row: number(row, "A_local_over_c")),
        morphed_rows[-1],
    ]

    fig, ax = plt.subplots(figsize=(10.5, 5.8), constrained_layout=True)
    ax.plot(x, upper_z, color=BLUE, lw=2.0, label="Baseline")
    ax.plot(x, lower_z, color=BLUE, lw=2.0)
    colors = [TEAL, GREEN, RED]
    for row, color in zip(selected, colors):
        amp = number(row, "A_local_over_c")
        result = morph_airfoil(x, upper_z, lower_z, number(row, "x_h_over_c", 0.62), amp)
        label = f"eta={number(row, 'eta'):.3f}, A/c={amp:.4f}"
        ax.plot(x, result.upper_z, color=color, lw=1.9, label=label)
        ax.plot(x, result.lower_z, color=color, lw=1.9)
    ax.axvline(0.62, color=ORANGE, ls="--", lw=1.8, label="x_h/c=0.62")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x/c")
    ax.set_ylabel("z/c")
    ax.set_title(f"{case_id}: representative morphed airfoil sections")
    ax.grid(alpha=0.22)
    ax.legend(fontsize=8.5, ncol=2)
    save_figure(fig, output, "02_strict_best_airfoil_sections")


def plot_trim_comparison(case_id: str, fast: dict | None, strict: dict, output: Path):
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.5), constrained_layout=True)
    labels = ["Fast search", "Strict validation"] if fast else ["Strict validation"]
    rows = [fast, strict] if fast else [strict]
    colors = [TEAL, GREEN] if fast else [GREEN]

    axes[0].bar(labels, [number(row, "CL_error") for row in rows], color=colors)
    axes[0].axhline(0, color=GRAY, lw=1)
    axes[0].set_ylabel("CL error")
    axes[0].set_title("Fixed-lift trim accuracy")

    axes[1].bar(labels, [number(row, "CDi") for row in rows], color=colors)
    axes[1].set_ylabel("CDi")
    axes[1].set_title("Induced drag")

    axes[2].bar(labels, [abs(number(row, "hinge_torque_proxy_Nm")) for row in rows], color=colors)
    axes[2].set_ylabel("|Torque proxy| [N m]")
    axes[2].set_title("Morphing-region torque proxy")
    for ax in axes:
        ax.tick_params(axis="x", rotation=15)
        ax.grid(axis="y", alpha=0.24)
    save_figure(fig, output, "03_fast_vs_strict_validation")


def plot_spanwise_loads(case_id: str, loads: list[dict], output: Path):
    eta = np.asarray([number(row, "eta") for row in loads])
    dy = np.asarray([number(row, "dy") for row in loads])
    y = np.asarray([number(row, "y") for row in loads])
    lift = np.asarray([number(row, "lift_per_span_N_per_m") for row in loads])
    drag_i = np.asarray([number(row, "induced_drag_per_span_N_per_m") for row in loads])
    cl = np.asarray([number(row, "sectional_cl") for row in loads])
    hinge = np.asarray([number(row, "hinge_moment_proxy_Nm_per_m") for row in loads])

    fig, axes = plt.subplots(4, 1, figsize=(10.0, 11.5), sharex=True, constrained_layout=True)
    series = [
        (lift, "Lift per span [N/m]", GREEN),
        (drag_i, "Induced drag per span [N/m]", BLUE),
        (cl, "Sectional cl", PURPLE),
        (hinge, "Hinge-moment proxy [N m/m]", ORANGE),
    ]
    for ax, (values, ylabel, color) in zip(axes, series):
        ax.plot(eta, values, color=color, lw=2.2)
        ax.axvspan(0.60, 0.95, color=LIGHT_GREEN, alpha=0.65)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.24)
    axes[0].set_title(f"{case_id}: strict VSPAERO sectional loads")
    axes[-1].set_xlabel("eta = y/(b/2)")
    save_figure(fig, output, "04_strict_best_spanwise_loads")

    shear = np.cumsum((lift * dy)[::-1])[::-1]
    bending = np.asarray([
        np.sum(lift[index:] * dy[index:] * (y[index:] - y[index]))
        for index in range(len(y))
    ])
    torque = np.cumsum((hinge * dy)[::-1])[::-1]

    fig, axes = plt.subplots(3, 1, figsize=(10.0, 9.2), sharex=True, constrained_layout=True)
    integrated = [
        (shear, "Outboard shear [N]", GREEN),
        (bending, "Outboard bending moment [N m]", PURPLE),
        (torque, "Outboard torque proxy [N m]", ORANGE),
    ]
    for ax, (values, ylabel, color) in zip(axes, integrated):
        ax.plot(eta, values, color=color, lw=2.2)
        ax.axvspan(0.60, 0.95, color=LIGHT_GREEN, alpha=0.65)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.24)
    axes[0].set_title(f"{case_id}: integrated loads for actuator concept discussion")
    axes[-1].set_xlabel("eta = y/(b/2)")
    save_figure(fig, output, "05_strict_best_integrated_loads")


def make_summary_table(case_id: str, fast: dict | None, strict: dict) -> list[dict]:
    rows = []
    if fast:
        rows.append({"source": "fast_search", **fast})
    rows.append({"source": "strict_validation", **strict})
    return rows


def report_values(strict: dict, fast: dict | None):
    values = {
        "alpha": number(strict, "alpha_trim_deg"),
        "cl": number(strict, "CL"),
        "cl_error": number(strict, "CL_error"),
        "cd": number(strict, "CD"),
        "cdi": number(strict, "CDi"),
        "cm": number(strict, "Cm"),
        "bending": number(strict, "root_bending_moment_Nm"),
        "bending_inc": number(strict, "root_bending_increase_percent"),
        "torque": number(strict, "hinge_torque_proxy_Nm"),
        "morph_lift": number(strict, "morph_region_lift_N"),
        "seconds": number(strict, "evaluation_seconds"),
        "executions": number(strict, "vspaero_execution_count"),
    }
    if fast:
        values["fast_cdi"] = number(fast, "CDi")
        values["cdi_delta_pct"] = 100.0 * (values["cdi"] - values["fast_cdi"]) / values["fast_cdi"]
        values["fast_cl_error"] = number(fast, "CL_error")
    return values


def write_reports(
    case_id: str,
    output_root: Path,
    plot_root: Path,
    fast: dict | None,
    strict: dict,
    history_rows: list[dict],
):
    values = report_values(strict, fast)
    config_path = output_root.parents[2] / "config" / "optimization_config.json"
    opt_config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    bending_limit = float(opt_config.get("root_bending_increase_limit_percent", 7.0))
    torque_limit = float(opt_config.get("hinge_torque_proxy_limit_Nm", 1100.0))
    feasible_text = str(strict.get("feasible", "")).lower() == "true"
    feasible = (
        values["bending_inc"] <= bending_limit
        and abs(values["torque"]) <= torque_limit
        and feasible_text
    )
    margin = bending_limit - values["bending_inc"]
    figures = [
        "01_strict_best_spanwise_schedule.svg",
        "02_strict_best_airfoil_sections.svg",
        "03_fast_vs_strict_validation.svg",
        "04_strict_best_spanwise_loads.svg",
        "05_strict_best_integrated_loads.svg",
    ]
    figure_lines = "\n".join(f"- `plot/final_validation/{name}`" for name in figures)
    history_tail = history_rows[-1] if history_rows else {}

    en = f"""# ARGUS Final Design Validation Report

## Design

- Case: `{case_id}`
- Source: current best design from the user optimization loop.
- Morphing region: eta = 0.60 to 0.95.
- Hinge / morphing start line: x_h/c = 0.62.
- Validation mode: strict iterative fixed-CL VSPAERO trim.

## Strict Validation Result

- Trim angle of attack: {values['alpha']:.6f} deg
- CL: {values['cl']:.9f}
- CL error: {values['cl_error']:.3e}
- CD: {values['cd']:.9f}
- CDi: {values['cdi']:.9f}
- Cm: {values['cm']:.9f}
- Half-wing root bending moment: {values['bending']:.3f} N m
- Root bending increase versus baseline: {as_percent(values['bending_inc'])}
- Morphing-region hinge torque proxy: {values['torque']:.3f} N m
- Morphing-region lift: {values['morph_lift']:.3f} N
- VSPAERO executions: {values['executions']:.0f}
- Evaluation time: {values['seconds']:.1f} s
- Feasible under current strict constraints: `{feasible}`
- Root-bending margin to {bending_limit:.3f}% limit: {margin:.3f} percentage points

## Fast Search Versus Strict Validation

The previous optimization loop used fast trim for speed. This final package
reruns the selected design with strict iterative trim before it is used for
discussion with the actuator team.

Important: the selected fast-search design is very close to the root-bending
constraint. Under strict validation it is slightly above the current
{bending_limit:.3f}% limit, so it should be treated as a near-boundary
candidate rather than the final feasible optimum.

{f"- Fast-search CDi: {values['fast_cdi']:.9f}" if fast else "- No fast-search result was found."}
{f"- Strict-minus-fast CDi change: {values['cdi_delta_pct']:.4f}%" if fast else ""}
{f"- Fast-search CL error: {values['fast_cl_error']:.3e}" if fast else ""}

## Figures

{figure_lines}

All figures are saved as SVG, PDF, and PNG. Use SVG for editable PowerPoint
or Inkscape work.

## Current Optimization Status

- Exact/search samples after the latest optimization iteration: {history_tail.get('total_exact_samples', 'n/a')}
- Current best after iteration history: `{history_tail.get('best_case_after', case_id)}`
- Last iteration improvement: {history_tail.get('improvement_percent', 'n/a')} %

## Interpretation

This result is still a low-order aerodynamic concept result. The hinge torque
is a VLM sectional-moment proxy about the chosen morphing start line, not a
certified actuator sizing load. It is suitable for early actuator architecture
discussion and for ranking morphing concepts, but the final design should be
checked with higher-fidelity CFD and a structural load path model.
"""

    cn = f"""# ARGUS 最终方案严格复算报告

## 方案

- 方案编号：`{case_id}`
- 来源：当前用户优化循环中的最优方案。
- 变形区域：eta = 0.60 到 0.95。
- 变形起始线 / 近似铰线：x_h/c = 0.62。
- 验证方式：严格 iterative 固定升力 VSPAERO 配平。

## 严格复算结果

- 配平迎角：{values['alpha']:.6f} deg
- CL：{values['cl']:.9f}
- CL 误差：{values['cl_error']:.3e}
- CD：{values['cd']:.9f}
- CDi：{values['cdi']:.9f}
- Cm：{values['cm']:.9f}
- 半翼根部弯矩：{values['bending']:.3f} N m
- 相对基准根弯矩增加：{as_percent(values['bending_inc'])}
- 变形区域铰线力矩代理值：{values['torque']:.3f} N m
- 变形区域升力：{values['morph_lift']:.3f} N
- VSPAERO 调用次数：{values['executions']:.0f}
- 求解时间：{values['seconds']:.1f} s
- 在当前严格约束下是否可行：`{feasible}`
- 相对 {bending_limit:.3f}% 根弯矩限制的裕度：{margin:.3f} 个百分点

## 快速搜索与严格复算的关系

前面的优化循环为了提高迭代效率使用了 fast trim。这个最终包会把选中的
方案重新用严格 iterative trim 复算，然后再用于和执行器团队讨论。

重要：这个快速搜索选出的方案非常接近根弯矩约束边界。严格复算后它略微
超过当前 {bending_limit:.3f}% 限制，因此应该把它视为“接近边界的候选方案”，
而不是最终严格可行最优。

{f"- 快速搜索 CDi：{values['fast_cdi']:.9f}" if fast else "- 未找到快速搜索结果。"}
{f"- 严格复算相对快速结果的 CDi 变化：{values['cdi_delta_pct']:.4f}%" if fast else ""}
{f"- 快速搜索 CL 误差：{values['fast_cl_error']:.3e}" if fast else ""}

## 图

{figure_lines}

所有图都保存为 SVG、PDF 和 PNG。需要在 PPT 或 Inkscape 里修改文字、图例、
线条和尺寸时，优先使用 SVG。

## 当前优化状态

- 最新优化迭代后的样本数：{history_tail.get('total_exact_samples', 'n/a')}
- 迭代历史记录中的当前最优：`{history_tail.get('best_case_after', case_id)}`
- 最新一轮改善：{history_tail.get('improvement_percent', 'n/a')} %

## 解释

这个结果仍然是低阶气动概念设计结果。这里的铰线力矩是基于 VLM 分段力矩、
绕指定变形起始线积分得到的代理值，不是最终执行器额定载荷。它适合用于
早期执行器构型讨论和不同变形方案排序；最终设计仍需要更高保真 CFD 以及
结构传力路径模型验证。
"""

    process = f"""# ARGUS Optimization Process Handoff for ChatGPT / Codex

## Purpose

This file is meant to be uploaded or pasted into ChatGPT/Codex when continuing
the ARGUS morphing-wing optimization. It records the current state and how to
add new optimization results.

## Current Best

- Current best case: `{case_id}`
- Strict validation directory: `{output_root}`
- Figure directory: `{plot_root}`
- Strict CDi: {values['cdi']:.9f}
- Strict CL error: {values['cl_error']:.3e}
- Root bending increase: {as_percent(values['bending_inc'])}
- Hinge torque proxy: {values['torque']:.3f} N m
- Feasible after strict validation: {feasible}
- Root-bending margin to {bending_limit:.3f}% limit: {margin:.3f} percentage points

## Main Commands

Run another optimization iteration:

```powershell
I:\\ARGUS\\tools\\python-3.13.13-embed-amd64\\python.exe scripts\\18_run_user_optimization.py --config config\\optimization_user_config.json
```

Rebuild this final validation package:

```powershell
I:\\ARGUS\\tools\\python-3.13.13-embed-amd64\\python.exe scripts\\19_validate_best_design_package.py
```

Rebuild plots/reports only, without rerunning VSPAERO:

```powershell
I:\\ARGUS\\tools\\python-3.13.13-embed-amd64\\python.exe scripts\\19_validate_best_design_package.py --skip-vspaero
```

## When Sending Results Back

Please provide these files or paste their contents:

- `outputs/optimization/user_optimization/iteration_history.csv`
- `outputs/optimization/user_optimization/current_best_design.json`
- `outputs/final_design_package/{case_id}/{case_id}_optimization_result.csv`
- `outputs/final_design_package/{case_id}/{case_id}_spanwise_loads.csv`
- Any new error log ending in `_failure.log` or `_strict_validation.log`

## Latest Iteration History

```csv
{chr(10).join(','.join(row.keys()) if index == 0 else '' for index, row in enumerate(history_rows[:1]))}
{chr(10).join(','.join(str(row.get(key, '')) for key in history_rows[0].keys()) for row in history_rows) if history_rows else 'No history found.'}
```
"""

    (output_root / "ARGUS_final_validation_report_EN.md").write_text(en, encoding="utf-8")
    (output_root / "ARGUS_final_validation_report_CN.md").write_text(cn, encoding="utf-8")
    (output_root / "ARGUS_optimization_process_for_ChatGPT_Codex.md").write_text(
        process,
        encoding="utf-8",
    )


def main():
    args = parse_args()
    project = args.project.resolve()
    case_id = args.case_id or current_best_case(project)
    case_dir = prepare_case(project, case_id)
    if not args.skip_vspaero:
        run_strict_validation(args, case_dir)

    plot_root = project / "plot" / "final_validation" / case_id
    plot_root.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "legend.frameon": True,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })

    schedule = read_csv(case_dir / f"{case_id}_section_schedule.csv")
    strict = read_csv(case_dir / f"{case_id}_optimization_result.csv")[0]
    fast_path = case_dir / f"{case_id}_fast_search_result.csv"
    fast = read_csv(fast_path)[0] if fast_path.exists() else None
    loads = read_csv(case_dir / f"{case_id}_spanwise_loads.csv")
    history_path = project / "outputs" / "optimization" / "user_optimization" / "iteration_history.csv"
    history_rows = read_csv(history_path) if history_path.exists() else []

    plot_schedule(case_id, schedule, plot_root)
    plot_airfoil_sections(project, case_id, schedule, plot_root)
    plot_trim_comparison(case_id, fast, strict, plot_root)
    plot_spanwise_loads(case_id, loads, plot_root)
    write_csv(case_dir / f"{case_id}_fast_vs_strict_summary.csv", make_summary_table(case_id, fast, strict))
    write_reports(case_id, case_dir, plot_root, fast, strict, history_rows)
    print(f"Final validation package written to {case_dir}")
    print(f"Editable figures written to {plot_root}")


if __name__ == "__main__":
    main()


