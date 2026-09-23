"""Run the cross-platform external-structure interface demonstration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from argus_workflow import ExternalCommandStructuralEvaluator, StructuralRequest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "demo_output",
    )
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    request = StructuralRequest.from_dict(
        __import__("json").loads((here / "example_request.json").read_text(encoding="utf-8"))
    )
    solver = here / "mock_structural_solver.py"
    adapter = ExternalCommandStructuralEvaluator(
        [sys.executable, str(solver), "--input", "{input}", "--output", "{output}"]
    )
    result = adapter.evaluate(request, args.output)
    print(f"case: {result.case_id}")
    print(f"feasible: {result.feasible}")
    for name, value in result.metrics.items():
        print(f"{name}: {value:.6g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
