from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(r"studies\argus_twist_morphing")
DOE = PROJECT / "outputs" / "fixed_cl_doe"
CASES = PROJECT / "outputs" / "representative_cases"
OUTPUT = PROJECT / "plot" / "twist_doe"

LABELS = {
    "twist_baseline": "Baseline",
    "twist_bell_washin_4deg": "Bell wash-in +4 deg",
    "twist_bell_washout_4deg": "Bell wash-out -4 deg",
    "twist_uniform_washin_2deg": "Uniform wash-in +2 deg",
    "twist_uniform_washout_2deg": "Uniform wash-out -2 deg",
}
COLORS = {
    "twist_baseline": "#1f2937",
    "twist_bell_washin_4deg": "#1b7f5a",
    "twist_bell_washout_4deg": "#b64b3a",
    "twist_uniform_washin_2deg": "#3b82b8",
    "twist_uniform_washout_2deg": "#d28a2e",
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def save(fig, name):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for suffix in [".png", ".pdf", ".svg"]:
        kwargs = {"dpi": 220} if suffix == ".png" else {}
        fig.savefig(OUTPUT / f"{name}{suffix}", bbox_inches="tight", **kwargs)
    plt.close(fig)


def plot_twist_schedules(summary):
    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    for item in summary:
        case_id = item["case_id"]
        rows = read_csv(
            CASES / case_id / f"{case_id}_twist_schedule.csv"
        )
        ax.plot(
            [float(row["eta"]) for row in rows],
            [float(row["incremental_twist_deg"]) for row in rows],
            marker="o",
            ms=4,
            lw=2.1,
            color=COLORS[case_id],
            label=LABELS[case_id],
        )
    ax.axvspan(0.60, 0.95, color="#dce8df", alpha=0.55, label="Morphing region")
    ax.axhline(0.0, color="#666666", lw=0.8)
    ax.set_xlabel(r"Normalized span, $\eta=y/(b/2)$")
    ax.set_ylabel("Incremental twist [deg]")
    ax.set_title("Representative distributed-twist schedules")
    ax.grid(alpha=0.25)
    ax.legend(ncol=2, fontsize=9)
    save(fig, "01_representative_twist_schedules")


def plot_metrics(summary):
    cases = [row for row in summary if row["case_id"] != "twist_baseline"]
    labels = [LABELS[row["case_id"]].replace(" ", "\n", 1) for row in cases]
    metrics = [
        ("CDi_reduction_percent", r"$C_{D_i}$ reduction [%]"),
        ("root_bending_change_percent", "Root bending change [%]"),
        ("outer_lift_change_percent", "Outer-wing lift change [%]"),
        ("alpha_trim_deg", "Trim angle of attack [deg]"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.6))
    for ax, (key, title) in zip(axes.flat, metrics):
        values = [float(row[key]) for row in cases]
        colors = [COLORS[row["case_id"]] for row in cases]
        bars = ax.bar(range(len(cases)), values, color=colors)
        ax.axhline(0.0, color="#555555", lw=0.8)
        ax.set_xticks(range(len(cases)), labels, fontsize=8)
        ax.set_ylabel(title)
        ax.grid(axis="y", alpha=0.25)
        ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    fig.suptitle("Fixed-lift distributed-twist DOE: aerodynamic and load effects")
    fig.tight_layout()
    save(fig, "02_twist_doe_metric_comparison")


def plot_tradeoff(summary):
    fig, ax = plt.subplots(figsize=(8.4, 6.2))
    for row in summary:
        case_id = row["case_id"]
        ax.scatter(
            float(row["root_bending_change_percent"]),
            float(row["CDi_reduction_percent"]),
            s=95,
            color=COLORS[case_id],
            edgecolor="black",
            linewidth=0.5,
            zorder=3,
        )
        ax.annotate(
            LABELS[case_id],
            (
                float(row["root_bending_change_percent"]),
                float(row["CDi_reduction_percent"]),
            ),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=8.5,
        )
    ax.scatter(
        6.079819084334822,
        4.43260425609682,
        marker="*",
        s=230,
        color="#7c3f98",
        edgecolor="black",
        linewidth=0.7,
        label="Trailing-edge preferred candidate",
        zorder=4,
    )
    ax.axhline(0.0, color="#666666", lw=0.8)
    ax.axvline(0.0, color="#666666", lw=0.8)
    ax.set_xlabel("Half-wing root bending change [%]")
    ax.set_ylabel(r"Induced-drag reduction, $\Delta C_{D_i}$ [%]")
    ax.set_title("Drag-load authority of distributed twist")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9)
    save(fig, "03_twist_vs_trailing_edge_tradeoff")


def plot_loads(summary):
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    for item in summary:
        case_id = item["case_id"]
        rows = read_csv(DOE / f"{case_id}_spanwise_loads.csv")
        ax.plot(
            [float(row["eta"]) for row in rows],
            [float(row["lift_per_span_N_per_m"]) for row in rows],
            lw=2.1,
            color=COLORS[case_id],
            label=LABELS[case_id],
        )
    ax.axvspan(0.60, 0.95, color="#dce8df", alpha=0.55)
    ax.set_xlabel(r"Normalized span, $\eta=y/(b/2)$")
    ax.set_ylabel("Lift per span [N/m]")
    ax.set_title("Fixed-lift spanwise loading: wash-in versus wash-out")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9, ncol=2)
    save(fig, "04_twist_spanwise_load_comparison")


def main():
    summary = read_csv(DOE / "fixed_cl_twist_doe_summary.csv")
    plot_twist_schedules(summary)
    plot_metrics(summary)
    plot_tradeoff(summary)
    plot_loads(summary)
    print(f"Wrote comparison figures to {OUTPUT}")


if __name__ == "__main__":
    main()



