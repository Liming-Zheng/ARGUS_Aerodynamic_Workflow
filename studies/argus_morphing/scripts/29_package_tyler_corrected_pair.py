from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT / "outputs" / "tyler_validation_2026_07_29"
DEFAULT_DELIVERY = PROJECT / "outputs" / "deliveries" / "corrected_pair"
CASES = ("baseline_corrected", "mcv2_i002_c01")
NATIVE_CONDITION = (
    "Wing-only VSPAERO; Mach 0.1; fixed CL=0.428277635108; "
    "Vinf=100 ft/s; rho=0.002377 slug/ft^3; 3 wake iterations"
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--delivery", type=Path, default=DEFAULT_DELIVERY)
    return parser.parse_args()


def read_row(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def copy_case(source, delivery, case_id):
    source_dir = source / case_id
    target_dir = delivery / case_id
    target_dir.mkdir(parents=True, exist_ok=True)
    required_extensions = {".vsp3", ".lod", ".polar", ".history", ".vspaero"}
    required_suffixes = (
        "_design.json",
        "_optimization_result.csv",
        "_trim_trace.csv",
        "_spanwise_loads.csv",
        "_section_schedule.csv",
        "_section_table.csv",
        "_airfoil_fingerprints.csv",
    )
    for path in source_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() in required_extensions or path.name.endswith(required_suffixes):
            shutil.copy2(path, target_dir / path.name)
    missing = [
        extension
        for extension in required_extensions
        if not any(path.suffix.lower() == extension for path in target_dir.iterdir())
    ]
    if missing:
        raise FileNotFoundError(f"{case_id} is missing native files: {missing}")


def matched_summary(source):
    baseline = read_row(
        source
        / "baseline_corrected"
        / "baseline_corrected_optimization_result.csv"
    )
    candidate = read_row(
        source
        / "mcv2_i002_c01"
        / "mcv2_i002_c01_optimization_result.csv"
    )
    baseline_cdi = float(baseline["CDi"])
    candidate_cdi = float(candidate["CDi"])
    baseline_bending = float(baseline["root_bending_moment_Nm"])
    candidate_bending = float(candidate["root_bending_moment_Nm"])
    bending_change = 100.0 * (candidate_bending - baseline_bending) / baseline_bending
    adjacent = float(candidate["max_adjacent_delta"])
    return [
        {
            "case_id": "baseline_corrected",
            "alpha_trim_deg": baseline["alpha_trim_deg"],
            "CL": baseline["CL"],
            "CDi": baseline["CDi"],
            "CDi_delta_counts_vs_corrected_baseline": 0.0,
            "CDi_reduction_percent_vs_corrected_baseline": 0.0,
            "half_wing_root_bending_Nm": baseline_bending,
            "root_bending_change_percent_vs_corrected_baseline": 0.0,
            "max_adjacent_command_delta": 0.0,
            "adjacent_command_limit": 0.018,
            "adjacent_limit_utilization_percent": 0.0,
            "status": "matched_reference",
        },
        {
            "case_id": "mcv2_i002_c01",
            "alpha_trim_deg": candidate["alpha_trim_deg"],
            "CL": candidate["CL"],
            "CDi": candidate["CDi"],
            "CDi_delta_counts_vs_corrected_baseline": 10000.0
            * (candidate_cdi - baseline_cdi),
            "CDi_reduction_percent_vs_corrected_baseline": 100.0
            * (baseline_cdi - candidate_cdi)
            / baseline_cdi,
            "half_wing_root_bending_Nm": candidate_bending,
            "root_bending_change_percent_vs_corrected_baseline": bending_change,
            "max_adjacent_command_delta": adjacent,
            "adjacent_command_limit": 0.018,
            "adjacent_limit_utilization_percent": 100.0 * adjacent / 0.018,
            "status": (
                "geometry_validation_case; exceeds illustrative 6.8% bending screen"
                if bending_change > 6.8
                else "geometry_validation_case; within illustrative bending screen"
            ),
        },
    ]


def csv_columns(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


def whitespace_header(path, first_tokens):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        tokens = line.split()
        if tuple(tokens[: len(first_tokens)]) == first_tokens:
            return tokens
    return []


def vspaero_keys(path):
    return [
        line.split("=", 1)[0].strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if "=" in line
    ]


def dictionary_row(file_name, column):
    lower = column.lower().strip()
    row = {
        "file": file_name,
        "column": column,
        "quantity": column,
        "unit": "unverified native field",
        "frame_or_reference": "native VSPAERO convention",
        "condition": NATIVE_CONDITION,
        "status": "native-unverified",
        "notes": "Retained natively; check VSPAERO documentation before dimensional use.",
    }
    if lower in {"case_id", "status", "notes", "shape_type", "trim_mode"}:
        row.update(unit="text", frame_or_reference="not applicable", status="valid", notes="Identifier or metadata.")
    elif lower in {"morphed", "same_as_inboard", "feasible"}:
        note = "Logical flag."
        status = "valid"
        if lower == "feasible":
            status = "do-not-use"
            note = "Legacy worker flag references a historical baseline; use matched_pair_summary.csv instead."
        row.update(unit="boolean", frame_or_reference="not applicable", status=status, notes=note)
    elif lower in {"section_id", "station_index", "vspaero_execution_count", "iter", "vortexsheet", "trailvort"}:
        row.update(unit="integer", frame_or_reference="index", status="valid", notes="Index or counter.")
    elif lower in {"eta", "eta_start", "eta_end", "cl", "cl_error", "cd", "cdi", "cm", "mach", "soverb", "v/vref", "stallfact"} or re.fullmatch(r"c[flm][ioxyzstwh]*", lower):
        row.update(unit="1", frame_or_reference="VSPAERO or local dimensionless convention", status="valid", notes="Dimensionless quantity.")
    elif lower.startswith("a") and lower.endswith("_over_c") or lower in {
        "a_local_over_c",
        "te_displacement_over_c",
        "max_adjacent_delta",
        "max_adjacent_command_delta",
        "max_spanwise_slope",
        "x_h_over_c",
        "adjacent_command_limit",
    }:
        row.update(unit="1", frame_or_reference="local chord/span parameterization", status="valid", notes="Dimensionless geometry command.")
    elif lower in {"alpha_deg", "alpha_trim_deg", "aoa", "aoa_", "beta", "beta_"}:
        row.update(unit="deg", frame_or_reference="VSPAERO aerodynamic angles", status="valid", notes="Angle.")
    elif lower in {"xavg", "yavg", "zavg", "dspan", "chord", "diameter", "cref", "bref", "x_cg", "y_cg", "z_cg", "y_native_ft", "chord_native_ft", "te_displacement_native_ft"}:
        row.update(unit="ft", frame_or_reference="OpenVSP vehicle frame/native model", status="valid", notes="Native length; Lunit=ft.")
    elif lower in {"sref", "darea"}:
        row.update(unit="ft^2", frame_or_reference="OpenVSP reference/native strip", status="valid", notes="Native area.")
    elif lower in {"y_m", "chord_m", "te_displacement_m"}:
        row.update(unit="m", frame_or_reference="SI conversion from native model", status="valid", notes="Converted using 1 ft=0.3048 m.")
    elif lower in {"rho", "rho_"}:
        row.update(unit="slug/ft^3", frame_or_reference="native VSPAERO condition", status="valid", notes="Native density.")
    elif lower in {"vinf", "vinf_"}:
        row.update(unit="ft/s", frame_or_reference="freestream", status="valid", notes="Native freestream speed.")
    elif lower in {"root_bending_moment_nm", "half_wing_root_bending_nm"}:
        row.update(unit="N m", frame_or_reference="half-wing root; SI post-processing of native strips", status="valid", notes="Uses native ft geometry converted with 0.3048 m/ft and q from 100 ft/s, 0.002377 slug/ft^3.")
    elif lower in {"morph_region_lift_n"}:
        row.update(unit="N", frame_or_reference="half-wing eta=0.60 to 1.00", status="valid", notes="SI post-processing of native strip loads.")
    elif lower.endswith("_percent") or "utilization_percent" in lower:
        row.update(unit="%", frame_or_reference="stated comparison reference", status="valid", notes="Relative percentage.")
    elif lower == "cdi_delta_counts_vs_corrected_baseline":
        row.update(unit="drag count (1e-4)", frame_or_reference="corrected matched baseline", status="valid", notes="10000 times the CDi difference.")
    elif lower == "evaluation_seconds":
        row.update(unit="s", frame_or_reference="wall clock", status="valid", notes="Runtime.")
    return row


def build_dictionary(delivery):
    entries = []
    for path in sorted(delivery.rglob("*.csv")):
        if path.name in {"DATA_DICTIONARY.csv", "SHA256SUMS.csv"}:
            continue
        entries.extend(
            (str(path.relative_to(delivery)), column)
            for column in csv_columns(path)
        )
    for path in sorted(delivery.rglob("*.lod")):
        entries.extend(
            (str(path.relative_to(delivery)), column)
            for column in whitespace_header(path, ("Iter", "VortexSheet", "TrailVort"))
        )
    for path in sorted(delivery.rglob("*.polar")):
        entries.extend(
            (str(path.relative_to(delivery)), column)
            for column in whitespace_header(path, ("Beta", "Mach", "AoA"))
        )
    for path in sorted(delivery.rglob("*.history")):
        entries.extend(
            (str(path.relative_to(delivery)), column)
            for column in whitespace_header(path, ("Iter", "Mach", "AoA"))
        )
    for path in sorted(delivery.rglob("*.vspaero")):
        entries.extend(
            (str(path.relative_to(delivery)), column)
            for column in vspaero_keys(path)
        )
    write_csv(
        delivery / "DATA_DICTIONARY.csv",
        [dictionary_row(file_name, column) for file_name, column in entries],
    )


def write_checksums(delivery):
    rows = []
    for path in sorted(delivery.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.csv":
            continue
        rows.append(
            {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "file": str(path.relative_to(delivery)).replace("\\", "/"),
                "bytes": path.stat().st_size,
            }
        )
    write_csv(delivery / "SHA256SUMS.csv", rows)


def main():
    args = parse_args()
    source = args.source.resolve()
    delivery = args.delivery.resolve()
    delivery.mkdir(parents=True, exist_ok=True)
    for case_id in CASES:
        copy_case(source, delivery, case_id)
    shutil.copy2(source / "airfoil_interpolation_audit.csv", delivery / "airfoil_interpolation_audit.csv")
    shutil.copy2(source / "airfoil_interpolation_audit.json", delivery / "airfoil_interpolation_audit.json")

    summary = matched_summary(source)
    write_csv(source / "matched_pair_summary.csv", summary)
    write_csv(delivery / "matched_pair_summary.csv", summary)
    for row in summary:
        case_dir = delivery / row["case_id"]
        (case_dir / "alpha_trim.txt").write_text(
            f"{float(row['alpha_trim_deg']):.12f} deg\n",
            encoding="ascii",
        )

    candidate = summary[1]
    readme = f"""ARGUS corrected low-speed matched-pair delivery
Date: 2026-07-29

Purpose
-------
This package answers Tyler's request for a baseline and mcv2_i002_c01 generated
from one corrected script. SplitWingXSec-inserted airfoils are now linearly
blended between their original bracketing profiles. Original sections are not
replaced. See airfoil_interpolation_audit.json.

Operating point
---------------
Wing only; Mach 0.1; fixed CL=0.428277635108; Vinf=100 ft/s;
rho=0.002377 slug/ft^3; 3 wake iterations. Native OpenVSP geometry units are ft.
Both cases were independently trimmed with the iterative strict workflow.

Matched result
--------------
Corrected baseline CDi: {float(summary[0]['CDi']):.9f}
mcv2_i002_c01 CDi: {float(candidate['CDi']):.9f}
CDi change: {float(candidate['CDi_delta_counts_vs_corrected_baseline']):+.3f} drag counts
CDi reduction: {float(candidate['CDi_reduction_percent_vs_corrected_baseline']):.3f}%
Root-bending change: {float(candidate['root_bending_change_percent_vs_corrected_baseline']):.3f}%

Constraint interpretation
-------------------------
The 0.018 max-adjacent-command bound is an illustrative numerical smoothness
screen. It is not traceable to skin strain, manufacturing, or an actuator
allowable. The historical 6.8% root-bending screen is also illustrative.
After correcting the inserted airfoils, this unchanged mcv2 command produces
{float(candidate['root_bending_change_percent_vs_corrected_baseline']):.3f}% more
half-wing root bending than the matched corrected baseline, so it should be
treated as a RANS geometry-validation case, not as a corrected feasible optimum.
A new optimization on the corrected base geometry is required before replacing
the report's engineering candidate.

The withdrawn 1050 hinge-moment proxy is not evaluated or constrained here.
Tyler's pressure-integrated local moment about x_h/c=0.62 over eta=0.60 to 1.00
is the appropriate aerodynamic quantity for the RANS comparison.

Files
-----
Each case includes .vsp3, .lod, .polar, .history, .vspaero, alpha_trim.txt,
the design/section description, strict result, trim trace, and SI spanwise loads.
DATA_DICTIONARY.csv states quantity, unit, frame/reference and condition.
SHA256SUMS.csv provides file integrity and traceability.
"""
    (delivery / "README.txt").write_text(readme, encoding="utf-8")
    teams_reply = f"""Hi Tyler,

Thanks for catching the inserted-section issue. I have regenerated both the
baseline and mcv2_i002_c01 from one corrected script. The original sections are
kept unchanged, and each inserted section is now linearly blended between its
original bracketing airfoils before the morphing command is applied.

I am sending the matched pair with the native .vsp3, .lod, .polar, .history
and .vspaero files, plus alpha_trim, strip loads, an interpolation audit, a
short data dictionary and SHA256 checksums. Both cases are wing-only,
Mach 0.1, fixed CL=0.428277635108, with Vinf=100 ft/s and
rho=0.002377 slug/ft^3. The native geometry units are feet.

One important result from the corrected rerun: the corrected baseline has
CDi={float(summary[0]['CDi']):.9f}, and mcv2_i002_c01 has
CDi={float(candidate['CDi']):.9f}, a reduction of
{float(candidate['CDi_reduction_percent_vs_corrected_baseline']):.3f}%.
However, relative to the matched corrected baseline, the half-wing root
bending increase is {float(candidate['root_bending_change_percent_vs_corrected_baseline']):.3f}%.
That is above the old 6.8% study-level screen, so I am treating this mcv2 file
as the requested RANS validation geometry, not as a corrected feasible optimum.
I will rerun the optimization on the corrected baseline before replacing the
report candidate.

The 0.018 adjacent-command limit is an illustrative numerical smoothness
bound. It is not based on a skin-strain, manufacturing or actuator allowable,
so please describe it that way. The 1050 hinge-moment proxy remains withdrawn.
Your pressure-integrated local moment about x_h/c=0.62 over
0.60 <= eta <= 1.00 is the quantity I would like to use going forward.

Best,
Liming
"""
    (delivery / "TEAMS_REPLY.txt").write_text(teams_reply, encoding="utf-8")
    build_dictionary(delivery)
    write_checksums(delivery)
    print(f"Wrote Tyler delivery to {delivery}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

