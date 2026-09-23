"""Consistent inequality-constraint status and tolerance handling."""

from __future__ import annotations


def _one_status(
    name: str,
    value: float,
    limit: float,
    relative_tolerance: float,
    absolute_value: bool = False,
) -> dict[str, float | str | bool]:
    checked = abs(value) if absolute_value else value
    allowed = limit * (1.0 + relative_tolerance)
    utilization = checked / limit if limit else float("inf")
    return {
        "name": name,
        "value": value,
        "checked_value": checked,
        "limit": limit,
        "utilization": utilization,
        "active": utilization >= 1.0 - relative_tolerance,
        "feasible": checked <= allowed,
        "relative_tolerance": relative_tolerance,
    }


def constraint_status(
    *,
    root_bending_moment_Nm: float,
    root_bending_limit_Nm: float,
    max_abs_command: float,
    max_abs_command_limit: float,
    max_adjacent_delta: float,
    max_adjacent_delta_limit: float,
    relative_tolerance: float = 0.001,
    aerodynamic_moment_proxy_Nm: float | None = None,
    aerodynamic_moment_limit_Nm: float | None = None,
) -> dict[str, object]:
    """Return all inequality statuses and identify active constraints."""

    statuses = [
        _one_status(
            "absolute_root_bending",
            root_bending_moment_Nm,
            root_bending_limit_Nm,
            relative_tolerance,
        ),
        _one_status(
            "maximum_command_amplitude",
            max_abs_command,
            max_abs_command_limit,
            relative_tolerance,
            absolute_value=True,
        ),
        _one_status(
            "maximum_adjacent_control_delta",
            max_adjacent_delta,
            max_adjacent_delta_limit,
            relative_tolerance,
        ),
    ]
    if aerodynamic_moment_limit_Nm is not None:
        if aerodynamic_moment_proxy_Nm is None:
            raise ValueError("Moment value is required when its limit is enabled")
        statuses.append(
            _one_status(
                "aerodynamic_moment_proxy",
                aerodynamic_moment_proxy_Nm,
                aerodynamic_moment_limit_Nm,
                relative_tolerance,
                absolute_value=True,
            )
        )
    return {
        "constraints": statuses,
        "feasible": all(bool(item["feasible"]) for item in statuses),
        "active_constraints": [
            str(item["name"]) for item in statuses if bool(item["active"])
        ],
    }

