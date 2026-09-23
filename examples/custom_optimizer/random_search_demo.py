"""Minimal optimizer adapter; the discipline models are deliberately synthetic."""

from __future__ import annotations

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from argus_workflow import (  # noqa: E402
    AerodynamicResult,
    CoupledEvaluationPipeline,
    DesignPoint,
    GeometryArtifact,
    OperatingPoint,
)


class DemoGeometryGenerator:
    def generate(self, design: DesignPoint, output_dir: Path) -> GeometryArtifact:
        path = output_dir / "demo_geometry.vsp3"
        path.write_text("Interface demonstration only.\n", encoding="utf-8")
        return GeometryArtifact(
            case_id=design.case_id,
            geometry_path=path,
            length_unit="m",
            design_variables=design.variables,
        )


class DemoAerodynamicEvaluator:
    def evaluate(self, geometry, operating_point, output_dir) -> AerodynamicResult:
        amplitude = float(geometry.design_variables["amplitude"])
        cdiw = 0.0108 - 0.0012 * amplitude + 0.0010 * amplitude**2
        return AerodynamicResult(
            case_id=geometry.case_id,
            operating_point=operating_point.name,
            geometry_path=geometry.geometry_path,
            cl=float(operating_point.target_cl),
            cdiw=cdiw,
            half_wing_root_bending_n_m=100.0 + 20.0 * amplitude,
        )


def bending_constraint(aero, structure):
    return {"root_bending": aero.half_wing_root_bending_n_m / 112.0 - 1.0}


def main() -> None:
    random.seed(7)
    pipeline = CoupledEvaluationPipeline(
        DemoGeometryGenerator(),
        DemoAerodynamicEvaluator(),
        constraint_function=bending_constraint,
    )
    operating_point = OperatingPoint(name="demo", mach=0.1, target_cl=0.428277635108)
    output_root = Path(__file__).with_name("demo_output")

    records = []
    for index in range(12):
        amplitude = random.uniform(-0.1, 1.0)
        design = DesignPoint(
            case_id=f"demo_{index:03d}",
            concept="interface_demo",
            variables={"amplitude": amplitude},
        )
        records.append(pipeline.evaluate(design, operating_point, output_root))

    feasible = [record for record in records if record.feasible]
    best = min(feasible, key=lambda record: record.objective)
    print(f"Best exact case: {best.design.case_id}")
    print(f"amplitude = {best.design.variables['amplitude']:.6f}")
    print(f"CDiw = {best.objective:.9f}")
    print(f"constraints = {dict(best.constraints)}")


if __name__ == "__main__":
    main()
