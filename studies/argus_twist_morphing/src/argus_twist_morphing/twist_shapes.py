from __future__ import annotations

from collections.abc import Sequence


def smoothstep(value: float) -> float:
    """Cubic interpolation with zero slope at both endpoints."""
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def smooth_window(
    eta: float,
    eta_start: float,
    eta_end: float,
    transition_fraction: float = 0.15,
) -> float:
    """Return a spanwise window with smooth entry and exit transitions."""
    if not 0.0 <= eta_start < eta_end <= 1.0:
        raise ValueError("Require 0 <= eta_start < eta_end <= 1")
    if not 0.0 < transition_fraction <= 0.5:
        raise ValueError("transition_fraction must be in (0, 0.5]")
    if eta <= eta_start or eta >= eta_end:
        return 0.0

    width = eta_end - eta_start
    transition = transition_fraction * width
    if eta < eta_start + transition:
        return smoothstep((eta - eta_start) / transition)
    if eta > eta_end - transition:
        return smoothstep((eta_end - eta) / transition)
    return 1.0


def _linear_interpolation(
    eta: float,
    control_etas: Sequence[float],
    control_twists_deg: Sequence[float],
) -> float:
    if eta <= control_etas[0]:
        return float(control_twists_deg[0])
    if eta >= control_etas[-1]:
        return float(control_twists_deg[-1])
    for index in range(1, len(control_etas)):
        if eta <= control_etas[index]:
            left_eta = control_etas[index - 1]
            right_eta = control_etas[index]
            fraction = (eta - left_eta) / (right_eta - left_eta)
            return float(
                control_twists_deg[index - 1]
                + fraction
                * (control_twists_deg[index] - control_twists_deg[index - 1])
            )
    return float(control_twists_deg[-1])


def control_point_twist(
    eta: float,
    eta_start: float,
    eta_end: float,
    control_etas: Sequence[float],
    control_twists_deg: Sequence[float],
    transition_fraction: float = 0.15,
) -> float:
    """Interpolate an added twist schedule and taper it to zero at boundaries."""
    if len(control_etas) != len(control_twists_deg):
        raise ValueError("control_etas and control_twists_deg must have equal length")
    if len(control_etas) < 2:
        raise ValueError("At least two control points are required")
    if any(right <= left for left, right in zip(control_etas, control_etas[1:])):
        raise ValueError("control_etas must be strictly increasing")
    if control_etas[0] < eta_start or control_etas[-1] > eta_end:
        raise ValueError("Control points must lie inside the morphing region")
    if eta <= eta_start or eta >= eta_end:
        return 0.0

    raw_twist = _linear_interpolation(eta, control_etas, control_twists_deg)
    return raw_twist * smooth_window(
        eta,
        eta_start,
        eta_end,
        transition_fraction,
    )


def twist_schedule_metrics(
    control_etas: Sequence[float],
    control_twists_deg: Sequence[float],
) -> dict[str, float]:
    """Return simple actuator- and structure-oriented schedule metrics."""
    if len(control_etas) != len(control_twists_deg):
        raise ValueError("control_etas and control_twists_deg must have equal length")
    if len(control_etas) < 2:
        raise ValueError("At least two control points are required")

    slopes = [
        (right_twist - left_twist) / (right_eta - left_eta)
        for left_eta, right_eta, left_twist, right_twist in zip(
            control_etas,
            control_etas[1:],
            control_twists_deg,
            control_twists_deg[1:],
        )
    ]
    return {
        "max_abs_twist_deg": max(abs(value) for value in control_twists_deg),
        "max_adjacent_delta_deg": max(
            abs(right - left)
            for left, right in zip(control_twists_deg, control_twists_deg[1:])
        ),
        "max_spanwise_slope_deg_per_eta": max(abs(value) for value in slopes),
        "max_slope_change_deg_per_eta": max(
            (abs(right - left) for left, right in zip(slopes, slopes[1:])),
            default=0.0,
        ),
    }


