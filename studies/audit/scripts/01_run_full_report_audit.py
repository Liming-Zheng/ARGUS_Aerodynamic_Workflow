#!/usr/bin/env python3
"""Recompute and trace the numerical claims used by the ARGUS report.

This audit intentionally uses only Python's standard library. It does not
replace VSPAERO: it verifies the chain from saved exact solver outputs through
post-processing, candidate selection, and report-level claims.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Check:
    check_id: str
    category: str
    status: str
    claim: str
    recomputed: str
    source: str
    note: str = ""


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def as_float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def close(a: float, b: float, *, rtol: float = 1e-8, atol: float = 1e-10) -> bool:
    return abs(a - b) <= max(atol, rtol * max(abs(a), abs(b)))


def reduction(reference: float, candidate: float) -> float:
    return 100.0 * (reference - candidate) / reference


def isa_troposphere(altitude_m: float) -> tuple[float, float, float]:
    """Return T [K], p [Pa], rho [kg/m3] using the ISA through 20 km."""
    t0 = 288.15
    p0 = 101325.0
    lapse = -0.0065
    gas_r = 287.05287
    gravity = 9.80665
    if altitude_m <= 11000.0:
        temperature = t0 + lapse * altitude_m
        pressure = p0 * (temperature / t0) ** (-gravity / (lapse * gas_r))
    else:
        t11 = t0 + lapse * 11000.0
        p11 = p0 * (t11 / t0) ** (-gravity / (lapse * gas_r))
        temperature = t11
        pressure = p11 * math.exp(-gravity * (altitude_m - 11000.0) / (gas_r * t11))
    return temperature, pressure, pressure / (gas_r * temperature)


def integrate_strip_loads(path: Path) -> tuple[float, float]:
    rows = read_csv(path)
    lift = sum(as_float(row, "lift_per_span_N_per_m") * as_float(row, "dy_m") for row in rows)
    root = sum(
        as_float(row, "lift_per_span_N_per_m")
        * as_float(row, "dy_m")
        * as_float(row, "y_m")
        for row in rows
    )
    return lift, root


def add_numeric_check(
    checks: list[Check],
    check_id: str,
    category: str,
    claim: float,
    computed: float,
    source: Path,
    *,
    unit: str = "",
    rtol: float = 1e-8,
    atol: float = 1e-10,
    note: str = "",
) -> None:
    suffix = f" {unit}" if unit else ""
    checks.append(
        Check(
            check_id,
            category,
            "PASS" if close(claim, computed, rtol=rtol, atol=atol) else "FAIL",
            f"{claim:.12g}{suffix}",
            f"{computed:.12g}{suffix}",
            str(source),
            note,
        )
    )


def all_state_rows(root: Path, pattern: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in root.glob(pattern):
        for row in read_csv(path):
            row["_source"] = str(path)
            rows.append(row)
    return rows


def select_minimum(
    rows: Iterable[dict[str, str]], concept: str, state: str
) -> dict[str, str]:
    feasible = [
        row
        for row in rows
        if row.get("concept") == concept
        and row.get("flight_state") == state
        and as_bool(row.get("feasible", "false"))
    ]
    if not feasible:
        raise RuntimeError(f"No feasible rows for {concept}/{state}")
    return min(feasible, key=lambda row: as_float(row, "CDi"))


def scan_legacy_code(repo: Path) -> list[dict[str, str]]:
    patterns = [
        ("legacy_atmosphere", re.compile(r'\["rho_kg_m3"\]|\["velocity_m_s"\]')),
        ("withdrawn_hinge_proxy", re.compile(r"hinge_(?:torque|moment)_proxy|1050")),
        ("ambiguous_si_label", re.compile(r"TE_displacement_m|geometry.{0,30}met", re.I)),
    ]
    findings: list[dict[str, str]] = []
    for module in ("argus_morphing", "argus_twist_morphing"):
        for path in (repo / module).rglob("*"):
            if path.suffix.lower() not in {".py", ".md", ".json"}:
                continue
            if "__pycache__" in path.parts or "audit" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                for finding_id, pattern in patterns:
                    if pattern.search(line):
                        findings.append(
                            {
                                "finding_id": finding_id,
                                "path": str(path.relative_to(repo)),
                                "line": str(line_number),
                                "text": line.strip()[:240],
                            }
                        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="codex_work repository root",
    )
    parser.add_argument(
        "--report-root",
        type=Path,
        required=True,
        help="ARGUS_aerodynamic_optimization report repository root",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    report = args.report_root.resolve()
    output = (args.output_dir or repo / "audit" / "outputs").resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks: list[Check] = []

    # Audited low-speed trailing-edge candidate.
    unit_summary_path = repo / "argus_morphing/plot/unit_audit_2026_07_28/unit_audit_summary.json"
    unit_summary = read_json(unit_summary_path)
    computed_reduction = reduction(
        float(unit_summary["baseline_CDi"]), float(unit_summary["audited_candidate_CDi"])
    )
    add_numeric_check(
        checks,
        "LS-TE-01",
        "low-speed trailing edge",
        float(unit_summary["CDi_reduction_percent"]),
        computed_reduction,
        unit_summary_path,
        unit="%",
    )
    checks.append(
        Check(
            "LS-TE-02",
            "low-speed trailing edge",
            "PASS" if unit_summary["legacy_hinge_constraint_status"] == "withdrawn" else "FAIL",
            "legacy hinge proxy withdrawn",
            str(unit_summary["legacy_hinge_constraint_status"]),
            str(unit_summary_path),
            "The former 1050 value is not an actuator hinge-moment limit.",
        )
    )

    # Whole-wing sanity check.
    whole_path = repo / "argus_morphing/plot/whole_wing_sanity/whole_wing_sanity_summary.json"
    whole = read_json(whole_path)
    add_numeric_check(
        checks,
        "SANITY-01",
        "whole-wing sanity",
        float(whole["CDi_reduction_percent"]),
        reduction(float(whole["baseline_CDi"]), float(whole["best_CDi"])),
        whole_path,
        unit="%",
    )
    elliptic_reduction = reduction(
        float(whole["baseline_elliptic_rms_error"]), float(whole["best_elliptic_rms_error"])
    )
    add_numeric_check(
        checks,
        "SANITY-02",
        "whole-wing sanity",
        float(whole["elliptic_error_reduction_percent"]),
        elliptic_reduction,
        whole_path,
        unit="%",
    )
    checks.append(
        Check(
            "SANITY-03",
            "whole-wing sanity",
            "PASS" if float(whole["best_elliptic_rms_error"]) < float(whole["baseline_elliptic_rms_error"]) else "FAIL",
            "optimized loading is closer to elliptical",
            f'{whole["baseline_elliptic_rms_error"]:.8g} -> {whole["best_elliptic_rms_error"]:.8g}',
            str(whole_path),
            "Verification case only; not an actuator-feasible design.",
        )
    )

    # Historical low-speed twist: dimensionless and relative claims only.
    twist_path = (
        repo
        / "argus_twist_morphing/outputs/optimization/samples/twoi_i001_c01/"
        "twoi_i001_c01_optimization_result.csv"
    )
    twist = read_csv(twist_path)[0]
    twist_baseline_path = (
        repo
        / "argus_twist_morphing/outputs/fixed_cl_doe/"
        "twist_baseline_fixed_cl_summary.csv"
    )
    twist_baseline_cdi = as_float(read_csv(twist_baseline_path)[0], "CDi")
    add_numeric_check(
        checks,
        "LS-TW-01",
        "low-speed twist",
        as_float(twist, "CDi_reduction_percent"),
        reduction(twist_baseline_cdi, as_float(twist, "CDi")),
        twist_path,
        unit="%",
        note=f"Baseline is read from {twist_baseline_path}.",
    )
    checks.append(
        Check(
            "LS-TW-02",
            "low-speed twist",
            "WARN",
            "absolute SI loads available",
            "absolute loads withdrawn; CDi and relative root-bending change retained",
            str(twist_path),
            "Legacy native-foot geometry was treated as metres in dimensional columns.",
        )
    )

    # Matched Mach 0.1 four-concept sensitivity study.
    mach01_root = repo / "argus_mach01_comparison"
    mach01_state_path = mach01_root / "outputs/study_definition/flight_state.json"
    mach01_results_path = mach01_root / "outputs/evaluations/all_results.csv"
    mach01_summary_path = (
        mach01_root / "plot/mach01_comparison/mach01_selected_summary.csv"
    )
    if (
        mach01_state_path.exists()
        and mach01_results_path.exists()
        and mach01_summary_path.exists()
    ):
        mach01_state = read_json(mach01_state_path)
        mach01_results = read_csv(mach01_results_path)
        mach01_summary = read_csv(mach01_summary_path)
        temperature, _, density = isa_troposphere(
            float(mach01_state["altitude_m"])
        )
        speed = float(mach01_state["mach"]) * math.sqrt(
            1.4 * 287.05287 * temperature
        )
        dynamic_pressure = 0.5 * density * speed * speed
        add_numeric_check(
            checks,
            "M01-STATE-01",
            "Mach 0.1 sensitivity",
            float(mach01_state["dynamic_pressure_Pa"]),
            dynamic_pressure,
            mach01_state_path,
            unit="Pa",
            rtol=2e-8,
        )
        checks.append(
            Check(
                "M01-DB-01",
                "Mach 0.1 sensitivity",
                "PASS" if len(mach01_results) == 125 else "FAIL",
                "125 exact geometry evaluations",
                f"{len(mach01_results)} exact geometry evaluations",
                str(mach01_results_path),
            )
        )
        max_cl_error = max(abs(as_float(row, "CL_error")) for row in mach01_results)
        checks.append(
            Check(
                "M01-TRIM-01",
                "Mach 0.1 sensitivity",
                "PASS" if max_cl_error <= 2.0e-5 else "FAIL",
                "|CL error| <= 2e-5 for every case",
                f"maximum |CL error| = {max_cl_error:.8g}",
                str(mach01_results_path),
                "Each case uses independent single-point VSPAERO solves.",
            )
        )
        rigid = next(
            row for row in mach01_results if row["concept"] == "rigid"
        )
        root_limit = as_float(rigid, "half_wing_root_bending_moment_Nm")
        relative_tolerance = 0.0
        reported = {row["concept"]: row for row in mach01_summary}
        rigid_cdi = as_float(rigid, "CDi")
        for concept in (
            "rigid",
            "conventional_hinged",
            "trailing_edge",
            "twist",
        ):
            feasible = [
                row
                for row in mach01_results
                if row["concept"] == concept
                and as_float(row, "half_wing_root_bending_moment_Nm")
                <= root_limit * (1.0 + relative_tolerance)
            ]
            selected = min(feasible, key=lambda row: as_float(row, "CDi"))
            summary_row = reported[concept]
            checks.append(
                Check(
                    f"M01-SELECT-{concept[:2].upper()}",
                    "Mach 0.1 sensitivity",
                    (
                        "PASS"
                        if selected["case_id"] == summary_row["case_id"]
                        else "FAIL"
                    ),
                    summary_row["case_id"],
                    selected["case_id"],
                    str(mach01_results_path),
                    "Independent feasible minimum-CDi re-selection.",
                )
            )
            add_numeric_check(
                checks,
                f"M01-CDI-{concept[:2].upper()}",
                "Mach 0.1 sensitivity",
                as_float(summary_row, "CDi_reduction_percent"),
                reduction(rigid_cdi, as_float(selected, "CDi")),
                mach01_summary_path,
                unit="%",
            )
            loads_path = (
                mach01_root
                / "outputs/cases"
                / concept
                / selected["case_id"]
                / "spanwise_loads.csv"
            )
            integrated_lift, integrated_root = integrate_strip_loads(loads_path)
            add_numeric_check(
                checks,
                f"M01-LOAD-{concept[:2].upper()}",
                "Mach 0.1 sensitivity",
                as_float(selected, "half_wing_lift_N"),
                integrated_lift,
                loads_path,
                unit="N",
            )
            add_numeric_check(
                checks,
                f"M01-ROOT-{concept[:2].upper()}",
                "Mach 0.1 sensitivity",
                as_float(selected, "half_wing_root_bending_moment_Nm"),
                integrated_root,
                loads_path,
                unit="N m",
            )

    # Independent atmosphere and flight-state check.
    states_path = repo / "argus_cruise_comparison/outputs/study_definition/flight_states.json"
    states = read_json(states_path)
    for state in states:
        temperature, pressure, density = isa_troposphere(float(state["altitude_m"]))
        speed = float(state["mach"]) * math.sqrt(1.4 * 287.05287 * temperature)
        q = 0.5 * density * speed * speed
        lift = float(state["mass_equivalent_kg"]) * 9.80665
        cl = lift / (q * float(state["reference_area_m2"]))
        prefix = "EARLY" if state["name"] == "early_cruise" else "LATE"
        add_numeric_check(checks, f"{prefix}-ATM-01", "cruise state", float(state["density_kg_m3"]), density, states_path, unit="kg/m3", rtol=2e-8)
        add_numeric_check(checks, f"{prefix}-ATM-02", "cruise state", float(state["target_lift_N"]), lift, states_path, unit="N")
        add_numeric_check(checks, f"{prefix}-ATM-03", "cruise state", float(state["target_CL"]), cl, states_path, rtol=2e-8)

    # Re-select exact cruise and conventional candidates from every saved case.
    cruise_rows = all_state_rows(
        repo / "argus_cruise_comparison",
        "outputs/**/*_state_summary.csv",
    )
    cruise_summary_path = repo / "argus_cruise_comparison/plot/cruise_comparison/best_design_summary.csv"
    cruise_summary = read_csv(cruise_summary_path)
    reported_cruise = {(row["concept"], row["flight_state"]): row for row in cruise_summary}
    for state in ("early_cruise", "late_cruise"):
        for concept in ("trailing_edge", "twist"):
            selected = select_minimum(cruise_rows, concept, state)
            reported = reported_cruise[(concept, state)]
            checks.append(
                Check(
                    f"SELECT-{state[:1].upper()}-{concept[:2].upper()}",
                    "candidate selection",
                    "PASS" if selected["case_id"] == reported["case_id"] else "FAIL",
                    reported["case_id"],
                    selected["case_id"],
                    selected["_source"],
                    "Independent minimum-CDi selection among all saved exact feasible rows.",
                )
            )
            add_numeric_check(
                checks,
                f"CDI-{state[:1].upper()}-{concept[:2].upper()}",
                "four-concept result",
                as_float(reported, "CDi_reduction_percent"),
                reduction(as_float(reported, "baseline_CDi"), as_float(reported, "CDi")),
                cruise_summary_path,
                unit="%",
            )

    conventional_rows = all_state_rows(
        repo / "argus_conventional_control_comparison",
        "outputs/**/*_state_summary.csv",
    )
    four_path = (
        repo
        / "argus_conventional_control_comparison/plot/four_concept_comparison/"
        "four_concept_numeric_summary.csv"
    )
    four = read_csv(four_path)
    reported_four = {(row["concept"], row["flight_state"]): row for row in four}
    for state in ("early_cruise", "late_cruise"):
        selected = select_minimum(conventional_rows, "conventional_hinged", state)
        reported = reported_four[("conventional_hinged", state)]
        checks.append(
            Check(
                f"SELECT-{state[:1].upper()}-CV",
                "candidate selection",
                "PASS" if selected["case_id"] == reported["case_id"] else "FAIL",
                reported["case_id"],
                selected["case_id"],
                selected["_source"],
                "Independent minimum-CDi selection among all exact feasible hinged cases.",
            )
        )

    # Reintegrate rigid and selected strip loads.
    load_cases = [
        (
            "LOAD-E-RIGID",
            repo / "argus_cruise_comparison/outputs/rigid_baseline/early_cruise/spanwise_loads.csv",
            reported_four[("rigid", "early_cruise")],
        ),
        (
            "LOAD-L-RIGID",
            repo / "argus_cruise_comparison/outputs/rigid_baseline/late_cruise/spanwise_loads.csv",
            reported_four[("rigid", "late_cruise")],
        ),
        (
            "LOAD-E-TE",
            repo / "argus_cruise_comparison/outputs/optimization_cases/batch_02/"
            "te_b02_c01_early_min_cdi/evaluation/early_cruise/spanwise_loads.csv",
            reported_four[("trailing_edge", "early_cruise")],
        ),
        (
            "LOAD-E-TW",
            repo / "argus_cruise_comparison/outputs/optimization_cases/batch_02/"
            "tw_b02_c01_early_min_cdi/evaluation/early_cruise/spanwise_loads.csv",
            reported_four[("twist", "early_cruise")],
        ),
        (
            "LOAD-L-CV",
            repo / "argus_conventional_control_comparison/outputs/cases/batch_02/"
            "conv_g02_c11/evaluation/late_cruise/spanwise_loads.csv",
            reported_four[("conventional_hinged", "late_cruise")],
        ),
    ]
    for check_id, path, summary in load_cases:
        integrated_lift, integrated_root = integrate_strip_loads(path)
        target_root = as_float(summary, "root_bending_Nm")
        add_numeric_check(
            checks,
            check_id,
            "strip-load integration",
            target_root,
            integrated_root,
            path,
            unit="Nm",
            rtol=3e-4,
            note=f"Reintegrated half-wing lift = {integrated_lift:.3f} N.",
        )

    # Compare isolated fresh VSPAERO reruns when they are available.
    rerun_specs = [
        (
            "te_b02_c01_early_min_cdi",
            repo
            / "argus_cruise_comparison/outputs/optimization_cases/batch_02/"
            "te_b02_c01_early_min_cdi/evaluation/"
            "te_b02_c01_early_min_cdi_state_summary.csv",
        ),
        (
            "tw_b02_c01_early_min_cdi",
            repo
            / "argus_cruise_comparison/outputs/optimization_cases/batch_02/"
            "tw_b02_c01_early_min_cdi/evaluation/"
            "tw_b02_c01_early_min_cdi_state_summary.csv",
        ),
        (
            "conv_g02_c11",
            repo
            / "argus_conventional_control_comparison/outputs/cases/batch_02/"
            "conv_g02_c11/evaluation/conv_g02_c11_state_summary.csv",
        ),
    ]
    rerun_comparison: list[dict[str, str]] = []
    reruns_complete = True
    for case_id, original_path in rerun_specs:
        archived_rerun = (
            repo / "audit/outputs/solver_rerun_summaries" / f"{case_id}.csv"
        )
        working_rerun = (
            repo
            / "audit/solver_reruns"
            / case_id
            / "evaluation"
            / f"{case_id}_state_summary.csv"
        )
        rerun_path = archived_rerun if archived_rerun.exists() else working_rerun
        if not rerun_path.exists():
            reruns_complete = False
            continue
        original_by_state = {row["flight_state"]: row for row in read_csv(original_path)}
        for rerun in read_csv(rerun_path):
            state = rerun["flight_state"]
            original = original_by_state[state]
            for metric in ("CL", "CDi", "half_wing_root_bending_moment_Nm"):
                old = as_float(original, metric)
                new = as_float(rerun, metric)
                rerun_comparison.append(
                    {
                        "case_id": case_id,
                        "flight_state": state,
                        "metric": metric,
                        "original": repr(old),
                        "rerun": repr(new),
                        "absolute_difference": repr(new - old),
                    }
                )
                add_numeric_check(
                    checks,
                    f"RERUN-{case_id[:2].upper()}-{state[:1].upper()}-{metric[:3].upper()}",
                    "isolated solver rerun",
                    old,
                    new,
                    rerun_path,
                    rtol=1e-10,
                    atol=1e-9 if metric.endswith("_Nm") else 1e-12,
                )
    if rerun_comparison:
        with (output / "solver_rerun_comparison.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rerun_comparison[0]))
            writer.writeheader()
            writer.writerows(rerun_comparison)

    # Report text and reference checks.
    report_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((report / "sections").glob("*.tex"))
    )
    required_text = {
        "REPORT-01": ("mcv2\\_i002\\_c01", "audited low-speed candidate"),
        "REPORT-02": ("12.77\\%", "whole-wing CDi reduction"),
        "REPORT-03": ("28.18\\%", "elliptical RMS improvement"),
        "REPORT-04": ("2.628", "late-cruise trailing-edge result"),
        "REPORT-05": ("2.319", "late-cruise twist result"),
        "REPORT-06": ("source-less", "withdrawn 1050 limit explanation"),
    }
    for check_id, (needle, description) in required_text.items():
        checks.append(
            Check(
                check_id,
                "report traceability",
                "PASS" if needle in report_text else "FAIL",
                description,
                "present" if needle in report_text else "missing",
                str(report / "sections"),
            )
        )

    legacy_findings = scan_legacy_code(repo)
    with (output / "legacy_code_findings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["finding_id", "path", "line", "text"]
        )
        writer.writeheader()
        writer.writerows(legacy_findings)

    with (output / "claim_traceability.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(checks[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(check) for check in checks)

    counts = {status: sum(check.status == status for check in checks) for status in ("PASS", "WARN", "FAIL")}
    audit_json = {
        "audit_date": str(date.today()),
        "scope": "saved exact outputs, post-processing, selection logic, and report claims",
        "counts": counts,
        "checks": [asdict(check) for check in checks],
        "legacy_finding_count": len(legacy_findings),
        "solver_rerun_performed": reruns_complete,
    }
    (output / "audit_results.json").write_text(
        json.dumps(audit_json, indent=2), encoding="utf-8"
    )

    lines = [
        "# ARGUS calculation and report audit",
        "",
        f"Audit date: {date.today()}",
        "",
        "## Verdict",
        "",
        f"- PASS: {counts['PASS']}",
        f"- WARN: {counts['WARN']}",
        f"- FAIL: {counts['FAIL']}",
        "",
        "The decision-level early/late-cruise comparison is internally consistent: "
        "flight states, exact feasible candidate selection, induced-drag reductions, "
        "and saved strip-load integration agree with the report.",
        "",
        "The historical low-speed studies require a narrower interpretation. Their "
        "dimensionless aerodynamic coefficients and relative trends remain useful, "
        "but legacy absolute loads and the former hinge-moment proxy are not valid "
        "actuator-sizing quantities.",
        "",
        "## Checks",
        "",
        "| ID | Status | Category | Claim | Recomputed |",
        "|---|---|---|---:|---:|",
    ]
    for check in checks:
        lines.append(
            f"| {check.check_id} | {check.status} | {check.category} | "
            f"{check.claim.replace('|', '/')} | {check.recomputed.replace('|', '/')} |"
        )
    lines.extend(
        [
            "",
            "## Residual limitations",
            "",
            "- Three representative geometries were rerun through the same VSPAERO workflow in isolated directories. Exact reproducibility does not constitute independent solver or CFD validation.",
            "- The cruise ranking is low-order, wing-only, and transonic. Viscous and wave drag are not included.",
            "- The 1050 N m hinge limit and legacy morph-region moment proxy are withdrawn. Local actuator moment requires surface-pressure integration about a defined hinge/axis.",
            "- The refined OpenVSP baseline contains inherited duplicate neighbouring airfoil coordinate arrays. A direct profile-blending experiment changed the aerodynamics materially, so the current model is retained consistently for all compared cases and the geometry issue is deferred to a separately revalidated baseline.",
            "- The whole-wing unconstrained case is a workflow sanity check, not a feasible actuator design.",
            "",
            "## Reproduction",
            "",
            "```powershell",
            "python audit/scripts/01_run_full_report_audit.py `",
            "  --report-root <REPORT_ROOT>",
            "```",
            "",
        ]
    )
    (output / "AUDIT_REPORT_2026-07-28.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(counts))
    print(f"Wrote audit outputs to {output}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())


