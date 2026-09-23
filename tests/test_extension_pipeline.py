from pathlib import Path

from argus_workflow import (
    AerodynamicResult,
    CoupledEvaluationPipeline,
    DesignPoint,
    GeometryArtifact,
    OperatingPoint,
    StructuralResult,
)


class GeometryStub:
    def generate(self, design, output_dir):
        path = output_dir / f"{design.case_id}.vsp3"
        path.write_text("geometry stub\n", encoding="utf-8")
        return GeometryArtifact(
            case_id=design.case_id,
            geometry_path=path,
            length_unit="m",
            design_variables=design.variables,
        )


class AeroStub:
    def evaluate(self, geometry, operating_point, output_dir):
        loads = output_dir / "spanwise_loads.csv"
        loads.write_text("eta,lift_N_per_m\n0.6,100\n1.0,0\n", encoding="utf-8")
        return AerodynamicResult(
            case_id=geometry.case_id,
            operating_point=operating_point.name,
            geometry_path=geometry.geometry_path,
            cl=operating_point.target_cl,
            cdiw=0.0055,
            half_wing_root_bending_n_m=120.0,
            spanwise_loads_path=loads,
        )


class StructureStub:
    def evaluate(self, request, output_dir):
        return StructuralResult(
            schema_version="1.0",
            case_id=request.design.case_id,
            operating_point=request.operating_point.name,
            feasible=True,
            metrics={"mass_kg": 12.0, "max_strain": 0.002},
            constraints={"strain_limit": -0.6},
        )


def test_coupled_pipeline_writes_traceable_record(tmp_path: Path):
    pipeline = CoupledEvaluationPipeline(
        GeometryStub(), AeroStub(), StructureStub()
    )
    result = pipeline.evaluate(
        DesignPoint("demo", "trailing_edge", {"A1_over_c": 0.01}),
        OperatingPoint("low_speed", mach=0.1, target_cl=0.428277635108),
        tmp_path,
    )

    assert result.feasible
    assert result.objective == 0.0055
    assert result.constraints["strain_limit"] == -0.6
    assert (tmp_path / "demo" / "low_speed" / "evaluation_record.json").exists()


def test_positive_constraint_is_infeasible(tmp_path: Path):
    pipeline = CoupledEvaluationPipeline(
        GeometryStub(),
        AeroStub(),
        constraint_function=lambda aero, structure: {"bending_limit": 0.01},
    )
    result = pipeline.evaluate(
        DesignPoint("infeasible", "twist", {"twist_1_deg": 1.0}),
        OperatingPoint("low_speed", mach=0.1, target_cl=0.4),
        tmp_path,
    )
    assert not result.feasible
