import json
import sys
from pathlib import Path

from argus_workflow import (
    AerodynamicResult,
    DesignPoint,
    ExternalCommandStructuralEvaluator,
    GeometryArtifact,
    OperatingPoint,
    StructuralRequest,
)


def test_external_structural_adapter(tmp_path: Path):
    solver = Path(__file__).parents[1] / "examples" / "structural_coupling" / "mock_structural_solver.py"
    geometry = tmp_path / "demo.vsp3"
    loads = tmp_path / "loads.csv"
    geometry.write_text("demo\n", encoding="utf-8")
    loads.write_text("eta,lift_N_per_m\n", encoding="utf-8")
    request = StructuralRequest(
        schema_version="1.0",
        design=DesignPoint("demo", "trailing_edge", {"A1_over_c": 0.01}),
        operating_point=OperatingPoint("condition", 0.1, target_cl=0.4),
        geometry=GeometryArtifact("demo", geometry, "m", {"A1_over_c": 0.01}),
        aerodynamics=AerodynamicResult(
            "demo", "condition", geometry, 0.4, 0.005, 110.0, loads
        ),
    )
    adapter = ExternalCommandStructuralEvaluator(
        [sys.executable, str(solver), "--input", "{input}", "--output", "{output}"]
    )
    result = adapter.evaluate(request, tmp_path / "structural")
    assert result.case_id == "demo"
    assert "max_strain" in result.metrics
    assert json.loads((tmp_path / "structural" / "structural_result.json").read_text())["schema_version"] == "1.0"
