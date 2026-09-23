"""Versioned data models exchanged between ARGUS analysis disciplines."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"


def _path(value: str | Path) -> str:
    return str(Path(value).expanduser().resolve())


@dataclass(frozen=True)
class DesignPoint:
    case_id: str
    concept: str
    variables: Mapping[str, float]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatingPoint:
    name: str
    mach: float
    target_cl: float | None = None
    target_lift_n: float | None = None
    altitude_m: float | None = None
    density_kg_m3: float | None = None
    velocity_m_s: float | None = None
    reference_area_m2: float | None = None

    def __post_init__(self) -> None:
        targets = (self.target_cl is not None, self.target_lift_n is not None)
        if sum(targets) != 1:
            raise ValueError("Set exactly one of target_cl or target_lift_n.")
        if self.mach < 0:
            raise ValueError("Mach number must be non-negative.")


@dataclass(frozen=True)
class GeometryArtifact:
    case_id: str
    geometry_path: str
    length_unit: str
    design_variables: Mapping[str, float]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "geometry_path", _path(self.geometry_path))


@dataclass(frozen=True)
class AerodynamicResult:
    case_id: str
    operating_point: str
    geometry_path: str
    cl: float
    cdiw: float
    half_wing_root_bending_n_m: float
    spanwise_loads_path: str | None = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "geometry_path", _path(self.geometry_path))
        if self.spanwise_loads_path:
            object.__setattr__(self, "spanwise_loads_path", _path(self.spanwise_loads_path))


@dataclass(frozen=True)
class StructuralRequest:
    schema_version: str
    design: DesignPoint
    operating_point: OperatingPoint
    geometry: GeometryArtifact
    aerodynamics: AerodynamicResult
    requested_outputs: tuple[str, ...] = (
        "mass_kg",
        "max_stress_pa",
        "max_strain",
        "actuator_force_n",
        "actuator_stroke_m",
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StructuralRequest":
        return cls(
            schema_version=str(data["schema_version"]),
            design=DesignPoint(**data["design"]),
            operating_point=OperatingPoint(**data["operating_point"]),
            geometry=GeometryArtifact(**data["geometry"]),
            aerodynamics=AerodynamicResult(**data["aerodynamics"]),
            requested_outputs=tuple(data.get("requested_outputs", ())),
        )


@dataclass(frozen=True)
class StructuralResult:
    schema_version: str
    case_id: str
    operating_point: str
    feasible: bool
    metrics: Mapping[str, float]
    constraints: Mapping[str, float]
    files: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        invalid = [name for name, value in self.constraints.items() if not isinstance(value, (int, float))]
        if invalid:
            raise TypeError(f"Constraint values must be numeric: {invalid}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StructuralResult":
        return cls(**data)


@dataclass(frozen=True)
class EvaluationRecord:
    schema_version: str
    design: DesignPoint
    operating_point: OperatingPoint
    geometry: GeometryArtifact
    aerodynamics: AerodynamicResult
    objective: float
    constraints: Mapping[str, float]
    feasible: bool
    structure: StructuralResult | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
