"""Shape-preserving spanwise morphing schedules with a free wingtip."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Sequence


def _pchip_slopes(x: Sequence[float], y: Sequence[float]) -> list[float]:
    """Compute Fritsch-Carlson PCHIP slopes without a SciPy dependency."""

    n = len(x)
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    delta = [(y[i + 1] - y[i]) / h[i] for i in range(n - 1)]
    if n == 2:
        return [delta[0], delta[0]]

    slopes = [0.0] * n
    for i in range(1, n - 1):
        if delta[i - 1] == 0.0 or delta[i] == 0.0:
            slopes[i] = 0.0
        elif delta[i - 1] * delta[i] < 0.0:
            slopes[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            slopes[i] = (w1 + w2) / (
                w1 / delta[i - 1] + w2 / delta[i]
            )

    slopes[0] = ((2.0 * h[0] + h[1]) * delta[0] - h[0] * delta[1]) / (
        h[0] + h[1]
    )
    if slopes[0] * delta[0] <= 0.0:
        slopes[0] = 0.0
    elif delta[0] * delta[1] < 0.0 and abs(slopes[0]) > 3.0 * abs(delta[0]):
        slopes[0] = 3.0 * delta[0]

    slopes[-1] = (
        (2.0 * h[-1] + h[-2]) * delta[-1] - h[-1] * delta[-2]
    ) / (h[-1] + h[-2])
    if slopes[-1] * delta[-1] <= 0.0:
        slopes[-1] = 0.0
    elif delta[-1] * delta[-2] < 0.0 and abs(slopes[-1]) > 3.0 * abs(delta[-1]):
        slopes[-1] = 3.0 * delta[-1]
    return slopes


def _pchip_value(
    x: Sequence[float], y: Sequence[float], slopes: Sequence[float], value: float
) -> float:
    if value <= x[0]:
        return y[0]
    if value >= x[-1]:
        return y[-1]
    right = next(i for i in range(1, len(x)) if value <= x[i])
    left = right - 1
    h = x[right] - x[left]
    t = (value - x[left]) / h
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    return (
        h00 * y[left]
        + h10 * h * slopes[left]
        + h01 * y[right]
        + h11 * h * slopes[right]
    )


@dataclass(frozen=True)
class MorphingSchedule:
    eta_start: float
    eta_end: float
    active_control_etas: tuple[float, ...]
    active_values: tuple[float, ...]
    inboard_boundary_value: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.eta_start < self.eta_end <= 1.0:
            raise ValueError("Require 0 <= eta_start < eta_end <= 1")
        if len(self.active_control_etas) != len(self.active_values):
            raise ValueError("Control locations and values must have equal length")
        if not self.active_control_etas:
            raise ValueError("At least one active control is required")
        if self.active_control_etas[0] <= self.eta_start:
            raise ValueError("Active controls must lie outboard of the fixed boundary")
        if self.active_control_etas[-1] != self.eta_end:
            raise ValueError("The final active control must be at the free wingtip")
        if any(
            right <= left
            for left, right in zip(
                self.active_control_etas, self.active_control_etas[1:]
            )
        ):
            raise ValueError("Control locations must be strictly increasing")
        if not all(isfinite(value) for value in self.active_values):
            raise ValueError("Control values must be finite")

    @property
    def interpolation_etas(self) -> tuple[float, ...]:
        return (self.eta_start, *self.active_control_etas)

    @property
    def interpolation_values(self) -> tuple[float, ...]:
        return (self.inboard_boundary_value, *self.active_values)

    def value(self, eta: float) -> float:
        if eta <= self.eta_start:
            return self.inboard_boundary_value
        x = self.interpolation_etas
        y = self.interpolation_values
        return _pchip_value(x, y, _pchip_slopes(x, y), min(eta, self.eta_end))

    def sample(self, count: int = 401) -> list[tuple[float, float]]:
        if count < 2:
            raise ValueError("Sample count must be at least two")
        return [
            (
                self.eta_start
                + i * (self.eta_end - self.eta_start) / (count - 1),
                self.value(
                    self.eta_start
                    + i * (self.eta_end - self.eta_start) / (count - 1)
                ),
            )
            for i in range(count)
        ]

    def metrics(self, count: int = 401) -> dict[str, float]:
        sampled = self.sample(count)
        values = [value for _, value in sampled]
        etas = [eta for eta, _ in sampled]
        slopes = [
            (values[i + 1] - values[i]) / (etas[i + 1] - etas[i])
            for i in range(len(values) - 1)
        ]
        adjacent = [
            abs(right - left)
            for left, right in zip(
                self.interpolation_values, self.interpolation_values[1:]
            )
        ]
        return {
            "tip_value": self.active_values[-1],
            "max_abs_value_dense": max(abs(value) for value in values),
            "max_adjacent_control_delta": max(adjacent),
            "max_abs_spanwise_slope": max(abs(value) for value in slopes),
        }


def schedule_from_iterables(
    eta_start: float,
    eta_end: float,
    active_control_etas: Iterable[float],
    active_values: Iterable[float],
    inboard_boundary_value: float = 0.0,
) -> MorphingSchedule:
    return MorphingSchedule(
        eta_start=eta_start,
        eta_end=eta_end,
        active_control_etas=tuple(float(value) for value in active_control_etas),
        active_values=tuple(float(value) for value in active_values),
        inboard_boundary_value=float(inboard_boundary_value),
    )

