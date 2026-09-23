"""International Standard Atmosphere utilities for the cruise study."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, sqrt


G0 = 9.80665
R_AIR = 287.05287
GAMMA_AIR = 1.4
T0 = 288.15
P0 = 101325.0
LAPSE = 0.0065
T11 = 216.65
P11 = 22632.040095007793


@dataclass(frozen=True)
class AtmosphereState:
    altitude_m: float
    temperature_K: float
    pressure_Pa: float
    density_kg_m3: float
    speed_of_sound_m_s: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def isa_state(altitude_m: float) -> AtmosphereState:
    """Return ISA properties from sea level through 20 km."""

    if not 0.0 <= altitude_m <= 20000.0:
        raise ValueError("This study supports ISA altitudes from 0 to 20,000 m")
    if altitude_m <= 11000.0:
        temperature = T0 - LAPSE * altitude_m
        pressure = P0 * (temperature / T0) ** (G0 / (R_AIR * LAPSE))
    else:
        temperature = T11
        pressure = P11 * exp(-G0 * (altitude_m - 11000.0) / (R_AIR * T11))
    density = pressure / (R_AIR * temperature)
    speed_of_sound = sqrt(GAMMA_AIR * R_AIR * temperature)
    return AtmosphereState(
        altitude_m=altitude_m,
        temperature_K=temperature,
        pressure_Pa=pressure,
        density_kg_m3=density,
        speed_of_sound_m_s=speed_of_sound,
    )


def flight_state(
    name: str,
    altitude_m: float,
    mach: float,
    mass_equivalent_kg: float,
    reference_area_m2: float,
) -> dict[str, float | str]:
    """Build one physical flight state and its target lift coefficient."""

    if mach <= 0.0:
        raise ValueError("Mach number must be positive")
    if mass_equivalent_kg <= 0.0 or reference_area_m2 <= 0.0:
        raise ValueError("Mass-equivalent lift and reference area must be positive")
    atmosphere = isa_state(altitude_m)
    velocity = mach * atmosphere.speed_of_sound_m_s
    dynamic_pressure = 0.5 * atmosphere.density_kg_m3 * velocity**2
    target_lift = mass_equivalent_kg * G0
    target_cl = target_lift / (dynamic_pressure * reference_area_m2)
    return {
        "name": name,
        **atmosphere.to_dict(),
        "mach": mach,
        "velocity_m_s": velocity,
        "dynamic_pressure_Pa": dynamic_pressure,
        "mass_equivalent_kg": mass_equivalent_kg,
        "target_lift_N": target_lift,
        "target_CL": target_cl,
        "reference_area_m2": reference_area_m2,
    }

