"""Stable extension interfaces for the ARGUS multidisciplinary workflow."""

from .external_structure import ExternalCommandStructuralEvaluator
from .models import (
    AerodynamicResult,
    DesignPoint,
    EvaluationRecord,
    GeometryArtifact,
    OperatingPoint,
    StructuralRequest,
    StructuralResult,
)
from .pipeline import CoupledEvaluationPipeline

__all__ = [
    "AerodynamicResult",
    "CoupledEvaluationPipeline",
    "DesignPoint",
    "EvaluationRecord",
    "ExternalCommandStructuralEvaluator",
    "GeometryArtifact",
    "OperatingPoint",
    "StructuralRequest",
    "StructuralResult",
]
