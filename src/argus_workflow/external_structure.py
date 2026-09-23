"""Adapter for structural models implemented as external commands."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Sequence

from .models import StructuralRequest, StructuralResult


class ExternalCommandStructuralEvaluator:
    """Run a structural model without importing its implementation.

    Command tokens may contain ``{input}``, ``{output}``, and ``{workdir}``.
    Using an argument list and ``shell=False`` keeps the adapter portable across
    Windows, Linux, and macOS.
    """

    def __init__(self, command: Sequence[str], timeout_seconds: float = 3600.0):
        if not command:
            raise ValueError("Structural command cannot be empty.")
        self.command = tuple(str(token) for token in command)
        self.timeout_seconds = timeout_seconds

    def evaluate(self, request: StructuralRequest, output_dir: Path) -> StructuralResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        request_path = output_dir / "structural_request.json"
        result_path = output_dir / "structural_result.json"
        request_path.write_text(
            json.dumps(request.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

        substitutions = {
            "{input}": str(request_path.resolve()),
            "{output}": str(result_path.resolve()),
            "{workdir}": str(output_dir.resolve()),
        }
        command = [
            substitutions.get(token, token)
            for token in self.command
        ]
        completed = subprocess.run(
            command,
            cwd=output_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            shell=False,
        )
        (output_dir / "structural_stdout.txt").write_text(
            completed.stdout, encoding="utf-8"
        )
        (output_dir / "structural_stderr.txt").write_text(
            completed.stderr, encoding="utf-8"
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Structural command failed with exit code {completed.returncode}. "
                f"See {output_dir / 'structural_stderr.txt'}."
            )
        if not result_path.exists():
            raise FileNotFoundError(
                f"Structural command did not create {result_path}."
            )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        result = StructuralResult.from_dict(data)
        if result.case_id != request.design.case_id:
            raise ValueError("Structural result case_id does not match the request.")
        if result.operating_point != request.operating_point.name:
            raise ValueError("Structural result operating point does not match the request.")
        return result
