from __future__ import annotations

import math
from collections.abc import Sequence


SHAPE_TYPES = ("uniform", "tip_increasing", "tip_decreasing", "bell")


def normalized_span_coordinate(eta: float, eta_start: float, eta_end: float) -> float | None:
    if not 0.0 <= eta_start < eta_end <= 1.0:
        raise ValueError("Require 0 <= eta_start < eta_end <= 1")
    if eta < eta_start or eta > eta_end:
        return None
    return (eta - eta_start) / (eta_end - eta_start)


def spanwise_amplitude(
    eta: float,
    eta_start: float,
    eta_end: float,
    amplitude_max_over_c: float,
    shape_type: str,
) -> float:
    r = normalized_span_coordinate(eta, eta_start, eta_end)
    if r is None:
        return 0.0
    if shape_type == "uniform":
        factor = 1.0
    elif shape_type == "tip_increasing":
        factor = r
    elif shape_type == "tip_decreasing":
        factor = 1.0 - r
    elif shape_type == "bell":
        factor = math.sin(math.pi * r)
    else:
        raise ValueError(f"Unknown shape_type {shape_type!r}; choose from {SHAPE_TYPES}")
    return amplitude_max_over_c * factor


def control_point_amplitude(
    eta: float,
    eta_start: float,
    eta_end: float,
    control_etas: Sequence[float],
    control_amplitudes: Sequence[float],
) -> float:
    if len(control_etas) != len(control_amplitudes):
        raise ValueError("control_etas and control_amplitudes must have equal length")
    if len(control_etas) < 2:
        raise ValueError("At least two control points are required")
    if any(right <= left for left, right in zip(control_etas, control_etas[1:])):
        raise ValueError("control_etas must be strictly increasing")
    if control_etas[0] < eta_start or control_etas[-1] > eta_end:
        raise ValueError("Control points must lie inside the morphing region")
    if eta < eta_start or eta > eta_end:
        return 0.0
    if eta <= control_etas[0]:
        return float(control_amplitudes[0])
    if eta >= control_etas[-1]:
        return float(control_amplitudes[-1])
    for index in range(1, len(control_etas)):
        if eta <= control_etas[index]:
            left_eta = control_etas[index - 1]
            right_eta = control_etas[index]
            fraction = (eta - left_eta) / (right_eta - left_eta)
            return float(
                control_amplitudes[index - 1]
                + fraction
                * (control_amplitudes[index] - control_amplitudes[index - 1])
            )
    return float(control_amplitudes[-1])


def control_point_metrics(
    control_etas: Sequence[float],
    control_amplitudes: Sequence[float],
    include_boundary_zeros: bool = False,
) -> dict[str, float]:
    if len(control_etas) != len(control_amplitudes):
        raise ValueError("control_etas and control_amplitudes must have equal length")
    values = list(control_amplitudes)
    adjacent_values = [0.0, *values, 0.0] if include_boundary_zeros else values
    first_slopes = [
        (right_a - left_a) / (right_eta - left_eta)
        for left_eta, right_eta, left_a, right_a in zip(
            control_etas,
            control_etas[1:],
            control_amplitudes,
            control_amplitudes[1:],
        )
    ]
    return {
        "max_amplitude": max(abs(value) for value in values),
        "max_adjacent_delta": max(
            abs(right - left)
            for left, right in zip(adjacent_values, adjacent_values[1:])
        ),
        "max_spanwise_slope": max(abs(value) for value in first_slopes),
        "max_slope_change": max(
            (abs(right - left) for left, right in zip(first_slopes, first_slopes[1:])),
            default=0.0,
        ),
    }

