from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MorphedAirfoil:
    x: np.ndarray
    upper_z: np.ndarray
    lower_z: np.ndarray
    baseline_upper_z: np.ndarray
    baseline_lower_z: np.ndarray
    displacement: np.ndarray


def smoothstep(s: np.ndarray) -> np.ndarray:
    return 3.0 * s**2 - 2.0 * s**3


def camber_displacement(
    x: np.ndarray,
    x_h_over_c: float,
    amplitude_over_c: float,
) -> np.ndarray:
    """
    Return vertical camber displacement.

    Project convention: positive amplitude means trailing edge down. Airfoil z
    is positive upward, so positive amplitude produces negative displacement.
    """
    if not 0.0 < x_h_over_c < 1.0:
        raise ValueError("x_h_over_c must lie strictly between 0 and 1")
    displacement = np.zeros_like(x, dtype=float)
    aft = x >= x_h_over_c
    s = (x[aft] - x_h_over_c) / (1.0 - x_h_over_c)
    displacement[aft] = -amplitude_over_c * smoothstep(s)
    return displacement


def morph_airfoil(
    x: np.ndarray,
    upper_z: np.ndarray,
    lower_z: np.ndarray,
    x_h_over_c: float,
    amplitude_over_c: float,
) -> MorphedAirfoil:
    if not (len(x) == len(upper_z) == len(lower_z)):
        raise ValueError("x, upper_z, and lower_z must have equal length")
    displacement = camber_displacement(x, x_h_over_c, amplitude_over_c)
    return MorphedAirfoil(
        x=x.copy(),
        upper_z=upper_z + displacement,
        lower_z=lower_z + displacement,
        baseline_upper_z=upper_z.copy(),
        baseline_lower_z=lower_z.copy(),
        displacement=displacement,
    )


def equivalent_flap_angle_deg(x_h_over_c: float, amplitude_over_c: float) -> float:
    return float(np.degrees(np.arctan2(amplitude_over_c, 1.0 - x_h_over_c)))


def _orientation(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a, b, c, d, tolerance=1.0e-12) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    return (o1 * o2 < -tolerance) and (o3 * o4 < -tolerance)


def has_self_intersection(x: np.ndarray, upper_z: np.ndarray, lower_z: np.ndarray) -> bool:
    polygon = list(zip(reversed(x), reversed(upper_z))) + list(zip(x[1:], lower_z[1:]))
    segment_count = len(polygon) - 1
    for i in range(segment_count):
        for j in range(i + 2, segment_count):
            if i == 0 and j == segment_count - 1:
                continue
            if _segments_intersect(polygon[i], polygon[i + 1], polygon[j], polygon[j + 1]):
                return True
    return False


def curvature(x: np.ndarray, z: np.ndarray) -> np.ndarray:
    dz = np.gradient(z, x)
    d2z = np.gradient(dz, x)
    return d2z / np.power(1.0 + dz**2, 1.5)


def validate_morphed_airfoil(airfoil: MorphedAirfoil, x_h_over_c: float) -> dict:
    baseline_thickness = airfoil.baseline_upper_z - airfoil.baseline_lower_z
    new_thickness = airfoil.upper_z - airfoil.lower_z
    camber = 0.5 * (airfoil.upper_z + airfoil.lower_z)
    baseline_camber = 0.5 * (
        airfoil.baseline_upper_z + airfoil.baseline_lower_z
    )
    delta = camber - baseline_camber
    slope = np.gradient(delta, airfoil.x)
    hinge_index = int(np.argmin(np.abs(airfoil.x - x_h_over_c)))
    aft_curvature = curvature(airfoil.x, camber)[hinge_index:]
    return {
        "min_thickness_over_c": float(np.min(new_thickness)),
        "max_thickness_change": float(np.max(np.abs(new_thickness - baseline_thickness))),
        "te_displacement_over_c": float(delta[-1]),
        "hinge_displacement_abs": float(abs(delta[hinge_index])),
        "hinge_slope_abs": float(abs(slope[hinge_index])),
        "max_abs_aft_camber_curvature": float(np.max(np.abs(aft_curvature))),
        "self_intersection": has_self_intersection(
            airfoil.x, airfoil.upper_z, airfoil.lower_z
        ),
        "valid": bool(
            np.min(new_thickness) >= -1.0e-10
            and np.max(np.abs(new_thickness - baseline_thickness)) <= 1.0e-10
            and not has_self_intersection(airfoil.x, airfoil.upper_z, airfoil.lower_z)
        ),
    }


