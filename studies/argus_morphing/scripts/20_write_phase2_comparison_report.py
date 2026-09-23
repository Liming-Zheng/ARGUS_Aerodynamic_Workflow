from __future__ import annotations

import csv
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CASES = ["usr_i003_c03", "ph2b_i001_c03", "opt_s002"]
LABELS = {
    "usr_i003_c03": "Phase-1 minimum-CDi candidate",
    "ph2b_i001_c03": "Phase-2 balanced smooth candidate",
    "opt_s002": "Uniform A/c=0.02 reference candidate",
}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]):
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def number(row: dict, key: str) -> float:
    return float(row[key])


def strict_result(case_id: str) -> dict:
    path = (
        PROJECT
        / "outputs"
        / "final_design_package"
        / case_id
        / f"{case_id}_optimization_result.csv"
    )
    return read_csv(path)[0]


def design_values(case_id: str) -> dict:
    path = PROJECT / "outputs" / "optimization" / "samples" / case_id / f"{case_id}_design.json"
    if not path.exists():
        return {}
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def markdown_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row[key]) for key, _ in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body])


def main():
    baseline = next(
        row
        for row in read_csv(PROJECT / "outputs" / "exact_trim_loads" / "exact_trim_load_summary.csv")
        if row["case_id"] == "refined_baseline"
    )
    baseline_cdi = number(baseline, "CDi")
    baseline_bending = number(baseline, "half_wing_root_bending_moment_Nm")

    rows = []
    for case_id in CASES:
        result = strict_result(case_id)
        design = design_values(case_id)
        cdi = number(result, "CDi")
        bending = number(result, "root_bending_moment_Nm")
        rows.append({
            "case_id": case_id,
            "label": LABELS[case_id],
            "CDi": f"{cdi:.9f}",
            "CDi_reduction_vs_baseline_percent": f"{100.0 * (baseline_cdi - cdi) / baseline_cdi:.3f}",
            "root_bending_increase_percent": f"{number(result, 'root_bending_increase_percent'):.3f}",
            "hinge_torque_proxy_Nm": f"{number(result, 'hinge_torque_proxy_Nm'):.1f}",
            "max_adjacent_delta": f"{number(result, 'max_adjacent_delta'):.5f}",
            "A1_over_c": f"{number(result, 'A1_over_c'):.5f}",
            "Amax_over_c": f"{max(number(result, f'A{i}_over_c') for i in range(1, 6)):.5f}",
            "strict_feasible": result["feasible"],
            "note": design.get("notes", ""),
        })

    output = PROJECT / "outputs" / "final_design_package" / "phase2_comparison"
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "phase2_candidate_comparison.csv", rows)

    columns = [
        ("case_id", "Case"),
        ("label", "Meaning"),
        ("CDi", "Strict CDi"),
        ("CDi_reduction_vs_baseline_percent", "CDi reduction [%]"),
        ("root_bending_increase_percent", "Root bending inc. [%]"),
        ("hinge_torque_proxy_Nm", "Torque proxy [N m]"),
        ("max_adjacent_delta", "Max adjacent ΔA/c"),
        ("A1_over_c", "Root-side A1/c"),
        ("Amax_over_c", "Amax/c"),
        ("strict_feasible", "Strict feasible"),
    ]
    table = markdown_table(rows, columns)
    en = f"""# ARGUS Phase-2 Candidate Comparison

The phase-1 optimizer minimized `CDi` aggressively. It found a low-drag shape,
but strict validation showed that the best phase-1 candidate slightly exceeded
the root-bending constraint. Phase 2 therefore adds engineering-oriented terms:
root-bending margin, hinge-torque proxy, endpoint amplitude, and spanwise
smoothness.

Reference baseline:

- Baseline strict CDi: {baseline_cdi:.9f}
- Baseline half-wing root bending moment: {baseline_bending:.3f} N m

{table}

## Recommendation

`ph2b_i001_c03` is the best current presentation candidate if the aim is to
show a non-trivial morphing-wing shape with strict feasibility. It keeps a
meaningful induced-drag reduction while reducing the root-side jump compared
with the phase-1 minimum-CDi result.

`opt_s002` is the simplest engineering reference because it uses a uniform
amplitude, but it still has a sharp cutoff at the outer boundary of the
morphing region. It is useful as a clean baseline for explaining the method.

`usr_i003_c03` should be shown as the reason phase-2 optimization was needed:
it has the lowest CDi among these candidates, but it is slightly infeasible
after strict validation.
"""
    cn = f"""# ARGUS 第二阶段候选方案对比

第一阶段优化主要追求最小 `CDi`。它找到了较低诱导阻力的形状，但严格复算后
最优候选略微超过根弯矩约束。因此第二阶段加入了更工程化的项：根弯矩裕度、
铰线力矩代理、端部幅值和展向平滑性。

基准模型：

- 基准严格 CDi：{baseline_cdi:.9f}
- 基准半翼根部弯矩：{baseline_bending:.3f} N m

{table}

## 建议

如果目标是展示一个“有实际变形、严格可行、且比第一阶段更结构友好”的方案，
当前建议使用 `ph2b_i001_c03`。它保留了比较明显的诱导阻力降低，同时相比
第一阶段最低 CDi 方案减小了内侧交界处突变。

`opt_s002` 是最容易解释的工程参考方案，因为它使用 uniform A/c=0.02；
但它在变形区域外端仍然存在直接截断的问题，适合作为方法说明的基准。

`usr_i003_c03` 可以作为“为什么需要第二阶段优化”的例子：它的 CDi 更低，
但严格复算后略微不可行。
"""
    latex = r"""\section{Current optimization status}

The first optimization stage minimized induced drag coefficient, \(C_{D_i}\),
under approximate load constraints. The best phase-1 candidate reduced
induced drag, but strict validation showed that it slightly exceeded the
root-bending constraint. A second optimization stage was therefore introduced
with additional engineering-oriented penalties for root-bending margin,
hinge-torque proxy, endpoint amplitude, and spanwise smoothness.

\begin{table}[h]
\centering
\small
\begin{tabular}{lrrrrr}
\hline
Case & \(C_{D_i}\) & \(\Delta C_{D_i}\) [\%] & Root bend [\%] & Torque [N\,m] & Max \(\Delta A/c\) \\
\hline
""" + "\n".join(
        f"{row['case_id']} & {row['CDi']} & {row['CDi_reduction_vs_baseline_percent']} & "
        f"{row['root_bending_increase_percent']} & {row['hinge_torque_proxy_Nm']} & "
        f"{row['max_adjacent_delta']} \\\\"
        for row in rows
    ) + r"""
\hline
\end{tabular}
\caption{Strict VSPAERO comparison of the current ARGUS morphing-wing candidates.}
\label{tab:phase2-candidate-comparison}
\end{table}

At the current stage, \texttt{ph2b\_i001\_c03} is the preferred presentation
candidate because it remains strictly feasible while preserving a meaningful
induced-drag reduction and a smoother spanwise morphing schedule than the
phase-1 minimum-drag candidate.
"""
    (output / "ARGUS_phase2_candidate_comparison_EN.md").write_text(en, encoding="utf-8")
    (output / "ARGUS_phase2_candidate_comparison_CN.md").write_text(cn, encoding="utf-8")
    (output / "optimization_status_section.tex").write_text(latex, encoding="utf-8")
    print(f"Wrote phase-2 comparison report to {output}")


if __name__ == "__main__":
    main()

