from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_morphing.airfoil_io import (  # noqa: E402
    cosine_grid,
    interpolate_surfaces,
    read_openvsp_airfoil_csv,
    write_airfoil_dat,
)
from argus_morphing.airfoil_morphing import (  # noqa: E402
    equivalent_flap_angle_deg,
    morph_airfoil,
    validate_morphed_airfoil,
)


X_H_VALUES = [0.35, 0.50, 0.62]
AMPLITUDES = [-0.04, -0.02, -0.01, 0.00, 0.01, 0.02, 0.04]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument(
        "--section-id",
        type=int,
        default=4,
        help="Baseline section used for standalone validation; section 4 is eta=0.71.",
    )
    return parser.parse_args()


def case_name(section_id: int, x_h: float, amplitude: float) -> str:
    amplitude_text = f"{amplitude:+.3f}".replace("+", "p").replace("-", "m").replace(".", "p")
    hinge_text = f"{x_h:.2f}".replace(".", "p")
    return f"section_{section_id:02d}_xh_{hinge_text}_A_{amplitude_text}"


def write_checks(path: Path, rows: list[dict]):
    fields = [
        "case_id",
        "section_id",
        "x_h_over_c",
        "A_max_over_c",
        "equivalent_flap_angle_deg",
        "min_thickness_over_c",
        "max_thickness_change",
        "te_displacement_over_c",
        "hinge_displacement_abs",
        "hinge_slope_abs",
        "max_abs_aft_camber_curvature",
        "self_intersection",
        "valid",
        "sign_convention",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def save_figure(fig, base: Path):
    fig.savefig(Path(f"{base}.png"), dpi=200, bbox_inches="tight")
    fig.savefig(Path(f"{base}.svg"), bbox_inches="tight")
    plt.close(fig)


def main():
    args = parse_args()
    raw_airfoils = (
        args.project / "outputs" / "baseline" / "raw" / "baseline_airfoil_points.csv"
    )
    output = args.project / "outputs" / "airfoils"
    output.mkdir(parents=True, exist_ok=True)
    upper, lower = read_openvsp_airfoil_csv(raw_airfoils, args.section_id)
    x = cosine_grid(161)
    upper_z, lower_z = interpolate_surfaces(upper, lower, x)

    write_airfoil_dat(
        output / f"baseline_section_{args.section_id:02d}.dat",
        f"NASA EET baseline section {args.section_id}",
        x,
        upper_z,
        lower_z,
    )

    check_rows = []
    generated = {}
    for x_h in X_H_VALUES:
        for amplitude in AMPLITUDES:
            name = case_name(args.section_id, x_h, amplitude)
            result = morph_airfoil(x, upper_z, lower_z, x_h, amplitude)
            checks = validate_morphed_airfoil(result, x_h)
            row = {
                "case_id": name,
                "section_id": args.section_id,
                "x_h_over_c": x_h,
                "A_max_over_c": amplitude,
                "equivalent_flap_angle_deg": equivalent_flap_angle_deg(x_h, amplitude),
                **checks,
                "sign_convention": "positive A_max/c = trailing edge down",
            }
            check_rows.append(row)
            generated[(x_h, amplitude)] = result
            write_airfoil_dat(
                output / f"morphed_{name}.dat",
                name,
                x,
                result.upper_z,
                result.lower_z,
            )
    write_checks(
        output / f"airfoil_morphing_check_section_{args.section_id:02d}.csv",
        check_rows,
    )

    colors = plt.cm.coolwarm(np.linspace(0.05, 0.95, len(AMPLITUDES)))
    for x_h in X_H_VALUES:
        fig, ax = plt.subplots(figsize=(11.5, 5.5))
        ax.plot(x, upper_z, color="black", lw=1.5, ls="--", label="Baseline")
        ax.plot(x, lower_z, color="black", lw=1.5, ls="--")
        for amplitude, color in zip(AMPLITUDES, colors):
            if amplitude == 0.0:
                continue
            result = generated[(x_h, amplitude)]
            ax.plot(x, result.upper_z, color=color, lw=1.2, label=f"A/c={amplitude:+.2f}")
            ax.plot(x, result.lower_z, color=color, lw=1.2)
        ax.axvline(x_h, color="#237a72", lw=1.3, ls=":", label=f"x_h/c={x_h:.2f}")
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(-0.02, 1.02)
        ax.set_xlabel("x/c")
        ax.set_ylabel("z/c")
        ax.set_title(f"Thickness-preserving camber morphing, section {args.section_id}")
        ax.grid(alpha=0.25)
        ax.legend(
            ncol=1,
            fontsize=8,
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            borderaxespad=0.0,
        )
        save_figure(
            fig,
            output / f"airfoil_morphing_check_section_{args.section_id:02d}_xh_{x_h:.2f}",
        )

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True, constrained_layout=True)
    for ax, x_h in zip(axes, X_H_VALUES):
        for amplitude, color in zip(AMPLITUDES, colors):
            result = generated[(x_h, amplitude)]
            ax.plot(x, result.displacement, color=color, label=f"{amplitude:+.2f}")
        ax.axvline(x_h, color="black", ls=":", lw=1)
        ax.set_title(f"x_h/c={x_h:.2f}")
        ax.set_xlabel("x/c")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("Camber displacement z/c")
    axes[-1].legend(title="A_max/c", fontsize=8, loc="best")
    save_figure(fig, output / "airfoil_morphing_displacement_functions")

    invalid = [row["case_id"] for row in check_rows if not row["valid"]]
    if invalid:
        raise RuntimeError(f"Invalid generated airfoils: {invalid}")
    print(f"Generated and validated {len(check_rows)} airfoils in {output}")


if __name__ == "__main__":
    main()

