"""Validate completeness and native-file consistency of the far-field audit."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


NATIVE_SUFFIXES = [".polar", ".lod", ".history", ".vspaero"]


def read_polar(path: Path) -> dict[str, float]:
    lines = path.read_text(errors="replace").splitlines()
    header_index = next(
        index
        for index, line in enumerate(lines)
        if line.split()[:3] == ["Beta", "Mach", "AoA"]
    )
    fields = lines[header_index].split()
    numeric_rows = []
    for line in lines[header_index + 1 :]:
        parts = line.split()
        if len(parts) != len(fields):
            continue
        try:
            numeric_rows.append([float(value) for value in parts])
        except ValueError:
            continue
    if not numeric_rows:
        raise ValueError(f"No numeric result row in {path}")
    return dict(zip(fields, numeric_rows[-1]))


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    root = project / "outputs" / "far_field_audit"
    with (root / "all_results.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    case_dirs = sorted((root / "cases").iterdir())
    completed_case_dirs = [
        path for path in case_dirs if (path / "audit_complete.json").exists()
    ]
    issues: list[str] = []
    native_count = 0
    maximums = {
        "absolute_CL_error": 0.0,
        "absolute_CDi_native_error": 0.0,
        "absolute_CDiw_native_error": 0.0,
        "absolute_e_far_native_error": 0.0,
    }
    if len(completed_case_dirs) != len(case_dirs):
        issues.append(
            f"Only {len(completed_case_dirs)} of {len(case_dirs)} cases are complete"
        )
    expected_rows = 2 * len(completed_case_dirs)
    if len(rows) != expected_rows:
        issues.append(f"Expected {expected_rows} state rows; found {len(rows)}")
    for row in rows:
        case_id = row["case_id"]
        state = row["flight_state"]
        state_dir = root / "cases" / case_id / state
        native_dir = state_dir / "native"
        for suffix in NATIVE_SUFFIXES:
            path = native_dir / f"{case_id}{suffix}"
            if not path.exists():
                issues.append(f"Missing native file: {path}")
            else:
                native_count += 1
        polar = read_polar(native_dir / f"{case_id}.polar")
        cl = float(row["CL"])
        cdi = float(row["CDi_near_field"])
        cdiw = float(row["CDiw_far_field"])
        e_far = float(row["e_far_field_total_CL"])
        maximums["absolute_CL_error"] = max(
            maximums["absolute_CL_error"], abs(float(row["CL_error"]))
        )
        maximums["absolute_CDi_native_error"] = max(
            maximums["absolute_CDi_native_error"], abs(cdi - polar["CDi"])
        )
        maximums["absolute_CDiw_native_error"] = max(
            maximums["absolute_CDiw_native_error"], abs(cdiw - polar["CDiw"])
        )
        aspect_ratio = float(row["reference_aspect_ratio"])
        independently_computed_e = cl**2 / (math.pi * aspect_ratio * cdiw)
        maximums["absolute_e_far_native_error"] = max(
            maximums["absolute_e_far_native_error"],
            abs(e_far - polar["Ew"]),
            abs(e_far - independently_computed_e),
        )
    if maximums["absolute_CL_error"] > 2.0e-5:
        issues.append(f"Strict CL tolerance exceeded: {maximums['absolute_CL_error']}")
    for name in ["absolute_CDi_native_error", "absolute_CDiw_native_error"]:
        if maximums[name] > 5.0e-12:
            issues.append(f"Native coefficient mismatch in {name}: {maximums[name]}")
    if maximums["absolute_e_far_native_error"] > 5.0e-7:
        issues.append(
            "Far-field total-CL span-efficiency mismatch: "
            f"{maximums['absolute_e_far_native_error']}"
        )
    result = {
        "status": "PASS" if not issues else "FAIL",
        "case_count": len(case_dirs),
        "state_result_count": len(rows),
        "native_file_count": native_count,
        "maximum_errors": maximums,
        "issues": issues,
    }
    (root / "validation_summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

