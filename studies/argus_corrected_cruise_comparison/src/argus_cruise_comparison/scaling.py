"""Explicit wind-tunnel and full-aircraft scale definitions."""

from __future__ import annotations

from math import sqrt


def build_scale_definition(config: dict) -> dict[str, float | str]:
    native = config["native_geometry"]
    aircraft = config["aircraft_scale"]
    native_area = float(native["reference_area_model_units2"])
    native_span = float(native["reference_span_model_units"])
    native_chord = float(native["reference_chord_model_units"])
    target_area = float(aircraft["target_reference_area_m2"])

    metres_per_model_unit = sqrt(target_area / native_area)
    target_span = native_span * metres_per_model_unit
    target_chord = native_chord * metres_per_model_unit
    target_aspect_ratio = target_span**2 / target_area
    requested_ar = float(aircraft["reference_aspect_ratio"])
    if aircraft.get("preserve_reference_aspect_ratio", False):
        if abs(target_aspect_ratio - requested_ar) > 1.0e-10:
            raise ValueError(
                "Area-based scale does not preserve the configured reference aspect ratio"
            )

    return {
        "native_length_unit": native["length_unit"],
        "wind_tunnel_m_per_model_unit": float(
            native["model_unit_to_m_wind_tunnel"]
        ),
        "aircraft_m_per_model_unit": metres_per_model_unit,
        "aircraft_reference_area_m2": target_area,
        "aircraft_reference_span_m": target_span,
        "aircraft_reference_chord_m": target_chord,
        "aircraft_reference_aspect_ratio": target_aspect_ratio,
        "linear_scale_aircraft_over_wind_tunnel": metres_per_model_unit
        / float(native["model_unit_to_m_wind_tunnel"]),
        "reference_source": native["reference_source"],
    }


def dimensionalize_strip(
    strip: dict[str, float],
    dynamic_pressure_Pa: float,
    metres_per_model_unit: float,
) -> dict[str, float]:
    """Convert one native VSPAERO strip to full-scale dimensional quantities."""

    y_m = abs(float(strip["Yavg"])) * metres_per_model_unit
    dy_m = float(strip["dSpan"]) * metres_per_model_unit
    chord_m = float(strip["Chord"]) * metres_per_model_unit
    cl = float(strip["cl"])
    cd = float(strip.get("cd", 0.0))
    cdi = float(strip.get("cdi", 0.0))
    cmy = float(strip.get("cmy", 0.0))
    return {
        "y_m": y_m,
        "dy_m": dy_m,
        "chord_m": chord_m,
        "sectional_cl": cl,
        "sectional_cd": cd,
        "sectional_cdi": cdi,
        "sectional_cmy": cmy,
        "lift_per_span_N_per_m": dynamic_pressure_Pa * chord_m * cl,
        "drag_per_span_N_per_m": dynamic_pressure_Pa * chord_m * cd,
        "induced_drag_per_span_N_per_m": dynamic_pressure_Pa * chord_m * cdi,
        "pitch_moment_per_span_Nm_per_m": dynamic_pressure_Pa * chord_m**2 * cmy,
    }

