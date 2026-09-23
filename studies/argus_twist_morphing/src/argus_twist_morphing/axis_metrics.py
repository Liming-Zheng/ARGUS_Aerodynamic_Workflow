from __future__ import annotations

import math


def point_displacement(
    x_over_c: float,
    axis_x_over_c: float,
    chord_m: float,
    twist_delta_deg: float,
) -> tuple[float, float, float]:
    """Return local dx, dz, and travel for rigid rotation about a chordwise axis."""
    angle = math.radians(twist_delta_deg)
    radius = (x_over_c - axis_x_over_c) * chord_m
    dx = radius * (math.cos(angle) - 1.0)
    dz = radius * math.sin(angle)
    return dx, dz, math.hypot(dx, dz)


def edge_displacements(
    axis_x_over_c: float,
    chord_m: float,
    twist_delta_deg: float,
) -> dict[str, float]:
    """Return leading- and trailing-edge rigid-body displacement metrics."""
    le_dx, le_dz, le_travel = point_displacement(
        0.0, axis_x_over_c, chord_m, twist_delta_deg
    )
    te_dx, te_dz, te_travel = point_displacement(
        1.0, axis_x_over_c, chord_m, twist_delta_deg
    )
    return {
        "leading_edge_dx_m": le_dx,
        "leading_edge_dz_m": le_dz,
        "leading_edge_travel_m": le_travel,
        "trailing_edge_dx_m": te_dx,
        "trailing_edge_dz_m": te_dz,
        "trailing_edge_travel_m": te_travel,
    }


def shift_pitch_moment_coefficient(
    cmy_reference: float,
    sectional_cl: float,
    reference_x_over_c: float,
    axis_x_over_c: float,
) -> float:
    """Shift a sectional pitch-moment coefficient to a new chordwise axis.

    The sign follows the VSPAERO y-moment convention used by the existing
    workflow. The result is retained as an aerodynamic moment proxy because
    structural load paths and actuator mechanics are not represented.
    """
    return cmy_reference + sectional_cl * (
        reference_x_over_c - axis_x_over_c
    )

