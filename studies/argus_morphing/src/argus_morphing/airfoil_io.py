from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np


def read_openvsp_airfoil_csv(path: Path, section_id: int) -> tuple[np.ndarray, np.ndarray]:
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if int(row["section_id"]) == section_id:
                grouped[row["surface"]].append(
                    (float(row["x_over_c"]), float(row["z_over_c"]))
                )
    if not grouped["upper"] or not grouped["lower"]:
        raise ValueError(f"Section {section_id} was not found in {path}")
    return clean_surface(grouped["upper"]), clean_surface(grouped["lower"])


def clean_surface(points) -> np.ndarray:
    """Sort by x and average duplicate x locations."""
    bins: dict[float, list[float]] = defaultdict(list)
    for x, z in points:
        bins[round(float(x), 12)].append(float(z))
    return np.array(
        [(x, sum(values) / len(values)) for x, values in sorted(bins.items())],
        dtype=float,
    )


def cosine_grid(point_count: int = 161) -> np.ndarray:
    if point_count < 3:
        raise ValueError("point_count must be at least 3")
    theta = np.linspace(0.0, np.pi, point_count)
    return 0.5 * (1.0 - np.cos(theta))


def interpolate_surfaces(
    upper: np.ndarray,
    lower: np.ndarray,
    x_grid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    upper_z = np.interp(x_grid, upper[:, 0], upper[:, 1])
    lower_z = np.interp(x_grid, lower[:, 0], lower[:, 1])
    return upper_z, lower_z


def write_airfoil_dat(path: Path, name: str, x: np.ndarray, upper_z: np.ndarray, lower_z: np.ndarray):
    """Write conventional TE-upper -> LE -> TE-lower airfoil coordinates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [name]
    for x_i, z_i in zip(reversed(x), reversed(upper_z)):
        lines.append(f"{x_i:.8f} {z_i:.8f}")
    for x_i, z_i in zip(x[1:], lower_z[1:]):
        lines.append(f"{x_i:.8f} {z_i:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


