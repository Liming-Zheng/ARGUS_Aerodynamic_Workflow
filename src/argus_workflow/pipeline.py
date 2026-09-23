"""Composable geometry-aerodynamics-structure evaluation pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping, Protocol

from .models import (
    SCHEMA_VERSION,
    AerodynamicResult,
    DesignPoint,
    EvaluationRecord,
    GeometryArtifact,
    OperatingPoint,
    StructuralRequest,
    StructuralResult,
)


class GeometryGenerator(Protocol):
    def generate(self, design: DesignPoint, output_dir: Path) -> GeometryArtifact: ...


class AerodynamicEvaluator(Protocol):
    def evaluate(
        self,
        geometry: GeometryArtifact,
        operating_point: OperatingPoint,
        output_dir: Path,
    ) -> AerodynamicResult: ...


class StructuralEvaluator(Protocol):
    def evaluate(self, request: StructuralRequest, output_dir: Path) -> StructuralResult: ...


ObjectiveFunction = Callable[[AerodynamicResult, StructuralResult | None], float]
ConstraintFunction = Callable[
    [AerodynamicResult, StructuralResult | None], Mapping[str, float]
]


def induced_drag_objective(
    aerodynamic: AerodynamicResult, structure: StructuralResult | None
) -> float:
    """Default objective: minimize wake/Trefftz induced drag ``CDiw``."""

    return aerodynamic.cdiw


class CoupledEvaluationPipeline:
    """Run one traceable multidisciplinary candidate evaluation.

    Constraint values use the optimization convention ``g(x) <= 0``. The
    structural evaluator may be omitted for aerodynamic-only studies.
    """

    def __init__(
        self,
        geometry_generator: GeometryGenerator,
        aerodynamic_evaluator: AerodynamicEvaluator,
        structural_evaluator: StructuralEvaluator | None = None,
        objective_function: ObjectiveFunction = induced_drag_objective,
        constraint_function: ConstraintFunction | None = None,
    ) -> None:
        self.geometry_generator = geometry_generator
        self.aerodynamic_evaluator = aerodynamic_evaluator
        self.structural_evaluator = structural_evaluator
        self.objective_function = objective_function
        self.constraint_function = constraint_function

    def evaluate(
        self,
        design: DesignPoint,
        operating_point: OperatingPoint,
        work_root: str | Path,
    ) -> EvaluationRecord:
        case_dir = Path(work_root) / design.case_id / operating_point.name
        geometry_dir = case_dir / "geometry"
        aero_dir = case_dir / "aerodynamics"
        structure_dir = case_dir / "structure"
        geometry_dir.mkdir(parents=True, exist_ok=True)
        aero_dir.mkdir(parents=True, exist_ok=True)

        geometry = self.geometry_generator.generate(design, geometry_dir)
        aerodynamic = self.aerodynamic_evaluator.evaluate(
            geometry, operating_point, aero_dir
        )

        structure = None
        if self.structural_evaluator is not None:
            structure_dir.mkdir(parents=True, exist_ok=True)
            request = StructuralRequest(
                schema_version=SCHEMA_VERSION,
                design=design,
                operating_point=operating_point,
                geometry=geometry,
                aerodynamics=aerodynamic,
            )
            structure = self.structural_evaluator.evaluate(request, structure_dir)

        constraints: dict[str, float] = {}
        if structure is not None:
            constraints.update(structure.constraints)
        if self.constraint_function is not None:
            constraints.update(self.constraint_function(aerodynamic, structure))

        feasible = all(value <= 0.0 for value in constraints.values())
        if structure is not None:
            feasible = feasible and structure.feasible

        record = EvaluationRecord(
            schema_version=SCHEMA_VERSION,
            design=design,
            operating_point=operating_point,
            geometry=geometry,
            aerodynamics=aerodynamic,
            structure=structure,
            objective=float(self.objective_function(aerodynamic, structure)),
            constraints=constraints,
            feasible=feasible,
        )
        (case_dir / "evaluation_record.json").write_text(
            json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        return record
