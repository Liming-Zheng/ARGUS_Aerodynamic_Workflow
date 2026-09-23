from __future__ import annotations

import pytest

from argus_morphing.airfoil_refinement import (
    blend_profiles,
    bracket_indices,
    cosine_grid,
    interpolate_surface,
)


def test_bracket_indices_returns_exact_and_interpolated_locations():
    etas = [0.0, 0.5, 1.0]
    assert bracket_indices(etas, 0.5) == (1, 1, 0.0)
    assert bracket_indices(etas, 0.75) == (1, 2, 0.5)


def test_interpolate_surface_averages_duplicate_x_locations():
    surface = [(0.0, 0.0), (0.5, 0.1), (0.5, 0.3), (1.0, 0.0)]
    assert interpolate_surface(surface, [0.5]) == pytest.approx([0.2])


def test_blend_profiles_is_linear_in_span():
    x_grid = [0.0, 0.5, 1.0]
    first = (
        [(0.0, 0.0), (0.5, 0.1), (1.0, 0.0)],
        [(0.0, 0.0), (0.5, -0.1), (1.0, 0.0)],
    )
    second = (
        [(0.0, 0.0), (0.5, 0.3), (1.0, 0.0)],
        [(0.0, 0.0), (0.5, -0.2), (1.0, 0.0)],
    )
    upper, lower = blend_profiles(first, second, 0.25, x_grid)
    assert upper[1] == pytest.approx((0.5, 0.15))
    assert lower[1] == pytest.approx((0.5, -0.125))


def test_cosine_grid_includes_leading_and_trailing_edges():
    grid = cosine_grid(9)
    assert grid[0] == pytest.approx(0.0)
    assert grid[-1] == pytest.approx(1.0)
    assert all(right > left for left, right in zip(grid, grid[1:]))

