from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]


def save_figure(fig, path: Path):
    fig.savefig(Path(f"{path}.png"), dpi=200, bbox_inches="tight")
    fig.savefig(Path(f"{path}.svg"), bbox_inches="tight")
    plt.close(fig)


def main():
    root = PROJECT / "outputs" / "doe"
    summary = pd.read_csv(root / "minimal_doe_fixed_cl_summary.csv")
    refined = pd.read_csv(
        PROJECT
        / "outputs"
        / "refined_baseline"
        / "refined_baseline_vspaero_coefficients.csv"
    ).iloc[0]
    summary["delta_CD"] = summary["CD"] - refined["CD"]
    summary["delta_CDi"] = summary["CDi"] - refined["CDi"]
    summary["delta_Cm"] = summary["Cm"] - refined["Cm"]
    summary["CDi_change_percent"] = 100.0 * summary["delta_CDi"] / refined["CDi"]
    summary["CD_change_percent"] = 100.0 * summary["delta_CD"] / refined["CD"]
    summary["at_amplitude_boundary"] = summary["A_max_over_c"].abs() >= 0.04 - 1.0e-12
    summary = summary.sort_values(["CDi", "CD"])
    summary.to_csv(root / "minimal_doe_ranked.csv", index=False)
    summary.head(15).to_csv(root / "minimal_doe_top15.csv", index=False)

    baseline_row = {
        "CL": refined["CL"],
        "CD": refined["CD"],
        "CDi": refined["CDi"],
        "Cm": refined["Cm"],
    }
    with (root / "minimal_doe_baseline_reference.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(baseline_row))
        writer.writeheader()
        writer.writerow(baseline_row)

    colors = {
        "uniform": "#174a6b",
        "tip_increasing": "#b1532f",
        "tip_decreasing": "#237a72",
        "bell": "#76558f",
    }
    for metric, ylabel, filename in [
        ("CDi_change_percent", "Induced-drag change [%]", "CDi_change_vs_amplitude"),
        ("CD_change_percent", "Total-drag change [%]", "CD_change_vs_amplitude"),
        ("alpha_trim_deg", "Trim angle of attack [deg]", "trim_alpha_vs_amplitude"),
        ("Cm", "Pitching-moment coefficient", "Cm_vs_amplitude"),
    ]:
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True, constrained_layout=True)
        for ax, x_h in zip(axes, sorted(summary["x_h_over_c"].unique())):
            subset = summary[summary["x_h_over_c"] == x_h]
            for shape, group in subset.groupby("shape_type"):
                group = group.sort_values("A_max_over_c")
                ax.plot(
                    group["A_max_over_c"],
                    group[metric],
                    marker="o",
                    color=colors[shape],
                    label=shape.replace("_", " "),
                )
            ax.axvline(0.0, color="black", lw=0.8)
            if "change_percent" in metric:
                ax.axhline(0.0, color="black", lw=0.8, ls=":")
            ax.set_title(f"x_h/c={x_h:.2f}")
            ax.set_xlabel("A_max/c")
            ax.grid(alpha=0.25)
        axes[0].set_ylabel(ylabel)
        axes[-1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
        save_figure(fig, root / filename)

    best = summary.iloc[0]
    report = [
        "ARGUS minimal DOE summary",
        "",
        f"Cases: {len(summary)}",
        "Reference: refined wing-only baseline, fixed CL by three-point interpolation.",
        f"Baseline CL: {refined['CL']:.9f}",
        f"Baseline CD: {refined['CD']:.9f}",
        f"Baseline CDi: {refined['CDi']:.9f}",
        "",
        "Best induced-drag case in the sampled DOE:",
        f"case_id: {best['case_id']}",
        f"x_h/c: {best['x_h_over_c']:.2f}",
        f"A_max/c: {best['A_max_over_c']:+.3f}",
        f"shape_type: {best['shape_type']}",
        f"alpha_trim: {best['alpha_trim_deg']:.5f} deg",
        f"CDi: {best['CDi']:.9f}",
        f"CDi change: {best['CDi_change_percent']:+.3f} %",
        f"CD change: {best['CD_change_percent']:+.3f} %",
        f"Cm: {best['Cm']:.9f}",
        f"at amplitude boundary: {bool(best['at_amplitude_boundary'])}",
        "",
        "Interpretation:",
        "- This is a DOE screening result, not the final optimum.",
        "- Cases are compared on the same refined geometry and reference quantities.",
        "- Fixed-CL values are interpolated from alpha = 1, 2, 3 deg.",
        "- Selected candidates require exact trim and sectional-load reruns.",
        "- Boundary optima indicate that actuator/curvature constraints must be active.",
    ]
    (root / "minimal_doe_summary.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()


