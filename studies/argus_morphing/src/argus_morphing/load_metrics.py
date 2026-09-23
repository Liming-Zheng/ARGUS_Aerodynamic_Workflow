from __future__ import annotations

import math
from collections.abc import Sequence


def trapezoid(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y):
        raise ValueError("x and y must have the same length")
    return sum(
        0.5 * (y[i] + y[i - 1]) * (x[i] - x[i - 1])
        for i in range(1, len(x))
    )


def elliptic_distribution(y: Sequence[float], semi_span: float, total_lift: float) -> list[float]:
    if semi_span <= 0.0:
        raise ValueError("semi_span must be positive")
    # Integral from 0 to b/2 of sqrt(1-(y/(b/2))^2) dy = pi*b/8.
    scale = total_lift / (math.pi * semi_span / 4.0)
    return [scale * math.sqrt(max(0.0, 1.0 - (yi / semi_span) ** 2)) for yi in y]


def normalized_distribution(y: Sequence[float], lift_per_span: Sequence[float]) -> list[float]:
    total = trapezoid(y, lift_per_span)
    if abs(total) < 1.0e-12:
        return [0.0 for _ in lift_per_span]
    return [value / total for value in lift_per_span]


def elliptic_error(y: Sequence[float], lift_per_span: Sequence[float], semi_span: float) -> float:
    total = trapezoid(y, lift_per_span)
    reference = elliptic_distribution(y, semi_span, total)
    actual_norm = normalized_distribution(y, lift_per_span)
    reference_norm = normalized_distribution(y, reference)
    squared_error = [(a - b) ** 2 for a, b in zip(actual_norm, reference_norm)]
    return trapezoid(y, squared_error)


def root_bending_moment(y: Sequence[float], lift_per_span: Sequence[float]) -> float:
    return trapezoid(y, [load * arm for load, arm in zip(lift_per_span, y)])


def strip_root_bending_moment(
    y: Sequence[float],
    widths: Sequence[float],
    lift_per_span: Sequence[float],
) -> float:
    if not (len(y) == len(widths) == len(lift_per_span)):
        raise ValueError("y, widths, and lift_per_span must have the same length")
    return sum(load * width * arm for load, width, arm in zip(lift_per_span, widths, y))


def outer_lift_fraction(
    eta: Sequence[float],
    y: Sequence[float],
    lift_per_span: Sequence[float],
    eta_start: float,
) -> float:
    total = trapezoid(y, lift_per_span)
    if abs(total) < 1.0e-12:
        return 0.0

    selected_y: list[float] = []
    selected_lift: list[float] = []
    for eta_i, y_i, lift_i in zip(eta, y, lift_per_span):
        if eta_i >= eta_start:
            selected_y.append(y_i)
            selected_lift.append(lift_i)
    if len(selected_y) < 2:
        return 0.0
    return trapezoid(selected_y, selected_lift) / total


def strip_outer_lift_fraction(
    eta: Sequence[float],
    widths: Sequence[float],
    lift_per_span: Sequence[float],
    eta_start: float,
) -> float:
    if not (len(eta) == len(widths) == len(lift_per_span)):
        raise ValueError("eta, widths, and lift_per_span must have the same length")
    strip_lift = [load * width for load, width in zip(lift_per_span, widths)]
    total = sum(strip_lift)
    if abs(total) < 1.0e-12:
        return 0.0
    return sum(value for value, eta_i in zip(strip_lift, eta) if eta_i >= eta_start) / total

