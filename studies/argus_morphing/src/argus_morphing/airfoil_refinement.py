from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence


Surface = list[tuple[float, float]]
Profile = tuple[Surface, Surface]


def clean_surface(points: Iterable[tuple[float, float]]) -> Surface:
    """Return an x-sorted surface with duplicate x locations averaged."""
    bins: dict[float, list[float]] = defaultdict(list)
    for x_value, z_value in points:
        bins[round(float(x_value), 12)].append(float(z_value))
    if len(bins) < 2:
        raise ValueError("An airfoil surface requires at least two x locations")
    return [
        (x_value, sum(values) / len(values))
        for x_value, values in sorted(bins.items())
    ]


def cosine_grid(point_count: int = 161) -> list[float]:
    if point_count < 3:
        raise ValueError("point_count must be at least 3")
    return [
        0.5 * (1.0 - math.cos(math.pi * index / (point_count - 1)))
        for index in range(point_count)
    ]


def interpolate_surface(surface: Sequence[tuple[float, float]], x_grid: Sequence[float]) -> list[float]:
    """Linearly interpolate one clean airfoil surface onto ``x_grid``."""
    cleaned = clean_surface(surface)
    x_values = [point[0] for point in cleaned]
    z_values = [point[1] for point in cleaned]
    output = []
    for x_value in x_grid:
        if x_value <= x_values[0]:
            output.append(z_values[0])
            continue
        if x_value >= x_values[-1]:
            output.append(z_values[-1])
            continue
        right = bisect_right(x_values, x_value)
        left = right - 1
        fraction = (x_value - x_values[left]) / (x_values[right] - x_values[left])
        output.append(
            z_values[left] + fraction * (z_values[right] - z_values[left])
        )
    return output


def bracket_indices(etas: Sequence[float], eta: float, tolerance: float = 1.0e-8) -> tuple[int, int, float]:
    """Return bracketing indices and interpolation fraction for a span station."""
    if not etas:
        raise ValueError("At least one original section is required")
    for index, original_eta in enumerate(etas):
        if abs(eta - original_eta) <= tolerance:
            return index, index, 0.0
    if eta <= etas[0]:
        return 0, 0, 0.0
    if eta >= etas[-1]:
        last = len(etas) - 1
        return last, last, 0.0
    right = bisect_right(etas, eta)
    left = right - 1
    fraction = (eta - etas[left]) / (etas[right] - etas[left])
    return left, right, fraction


def blend_profiles(
    inboard: Profile,
    outboard: Profile,
    fraction: float,
    x_grid: Sequence[float],
) -> Profile:
    """Blend upper and lower ordinates between two normalized airfoil profiles."""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must lie in [0, 1]")
    upper_in = interpolate_surface(inboard[0], x_grid)
    lower_in = interpolate_surface(inboard[1], x_grid)
    upper_out = interpolate_surface(outboard[0], x_grid)
    lower_out = interpolate_surface(outboard[1], x_grid)
    upper = [
        (x_value, left + fraction * (right - left))
        for x_value, left, right in zip(x_grid, upper_in, upper_out)
    ]
    lower = [
        (x_value, left + fraction * (right - left))
        for x_value, left, right in zip(x_grid, lower_in, lower_out)
    ]
    return upper, lower


def max_profile_difference(first: Profile, second: Profile) -> float:
    """Maximum coordinate difference for profiles already on the same grid."""
    values = []
    for first_surface, second_surface in zip(first, second):
        if len(first_surface) != len(second_surface):
            raise ValueError("Profiles must have matching point counts")
        for first_point, second_point in zip(first_surface, second_surface):
            values.extend(
                [
                    abs(first_point[0] - second_point[0]),
                    abs(first_point[1] - second_point[1]),
                ]
            )
    return max(values, default=0.0)

