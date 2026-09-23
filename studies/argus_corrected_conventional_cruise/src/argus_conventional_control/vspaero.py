"""Reusable OpenVSP/VSPAERO helpers for the cruise comparison study."""

from __future__ import annotations

import csv
from pathlib import Path


def set_int(vsp, analysis: str, name: str, value: int) -> None:
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetIntAnalysisInput(analysis, name, [int(value)], 0)


def set_double(vsp, analysis: str, name: str, value: float) -> None:
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetDoubleAnalysisInput(analysis, name, [float(value)], 0)


def set_string(vsp, analysis: str, name: str, value: str) -> None:
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetStringAnalysisInput(analysis, name, [str(value)], 0)


def _doubles(vsp, result_id: str, name: str) -> list[float]:
    try:
        return list(vsp.GetDoubleResults(result_id, name))
    except Exception:
        return []


def _last(vsp, result_id: str, names: list[str]) -> float:
    for name in names:
        values = _doubles(vsp, result_id, name)
        if values:
            return float(values[-1])
    raise RuntimeError(f"Missing VSPAERO result fields: {names}")


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write dictionaries while preserving the first-seen column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def configure_geometry(vsp, analysis_config: dict) -> None:
    analysis = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", analysis_config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_NONE)
    set_int(vsp, analysis, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(analysis)


def _configure_sweep(
    vsp,
    wing_id: str,
    alphas: list[float],
    mach: float,
    native_reference: dict,
    analysis_config: dict,
) -> str:
    analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(analysis)
    set_int(vsp, analysis, "AnalysisMethod", analysis_config["analysis_method"])
    set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
    set_int(vsp, analysis, "RefFlag", 0)
    set_double(
        vsp,
        analysis,
        "Sref",
        native_reference["reference_area_model_units2"],
    )
    set_double(
        vsp,
        analysis,
        "cref",
        native_reference["reference_chord_model_units"],
    )
    set_double(
        vsp,
        analysis,
        "bref",
        native_reference["reference_span_model_units"],
    )
    set_string(vsp, analysis, "WingID", wing_id)
    set_double(vsp, analysis, "AlphaStart", alphas[0])
    set_double(vsp, analysis, "AlphaEnd", alphas[-1])
    set_int(vsp, analysis, "AlphaNpts", len(alphas))
    set_double(vsp, analysis, "BetaStart", 0.0)
    set_double(vsp, analysis, "BetaEnd", 0.0)
    set_int(vsp, analysis, "BetaNpts", 1)
    set_double(vsp, analysis, "MachStart", mach)
    set_double(vsp, analysis, "MachEnd", mach)
    set_int(vsp, analysis, "MachNpts", 1)
    set_int(vsp, analysis, "WakeNumIter", analysis_config["wake_iterations"])
    return analysis


def evaluate(
    vsp,
    wing_id: str,
    alpha_deg: float,
    mach: float,
    native_reference: dict,
    analysis_config: dict,
    *,
    loads: bool = False,
) -> tuple[dict, list[dict]]:
    analysis = _configure_sweep(
        vsp,
        wing_id,
        [alpha_deg],
        mach,
        native_reference,
        analysis_config,
    )
    vsp.ExecAnalysis(analysis)
    history = vsp.FindLatestResultsID("VSPAERO_History")
    result = {
        "alpha_deg": float(alpha_deg),
        "CL": _last(vsp, history, ["CLtot", "CL"]),
        "CD": _last(vsp, history, ["CDtot", "CD"]),
        "CDi": _last(vsp, history, ["CDi"]),
        "Cm": _last(vsp, history, ["CMytot", "CMy", "Cm"]),
    }
    if not loads:
        return result, []

    load_id = vsp.FindLatestResultsID("VSPAERO_Load")
    names = list(vsp.GetAllDataNames(load_id))
    columns = {name: _doubles(vsp, load_id, name) for name in names}
    count = max((len(values) for values in columns.values()), default=0)
    rows = [
        {
            name: values[index]
            for name, values in columns.items()
            if index < len(values)
        }
        for index in range(count)
    ]
    return result, rows


def sweep_points(
    vsp,
    wing_id: str,
    alphas: list[float],
    mach: float,
    native_reference: dict,
    analysis_config: dict,
) -> list[dict]:
    count_before = vsp.GetNumResults("VSPAERO_History")
    analysis = _configure_sweep(
        vsp,
        wing_id,
        alphas,
        mach,
        native_reference,
        analysis_config,
    )
    vsp.ExecAnalysis(analysis)
    count_after = vsp.GetNumResults("VSPAERO_History")
    created = count_after - count_before
    if created < len(alphas):
        raise RuntimeError(
            f"Expected {len(alphas)} sweep results, VSPAERO created {created}"
        )
    result_ids = [
        vsp.FindResultsID("VSPAERO_History", index)
        for index in range(count_after - len(alphas), count_after)
    ]
    return [
        {
            "alpha_deg": alpha,
            "CL": _last(vsp, result_id, ["CLtot", "CL"]),
            "CD": _last(vsp, result_id, ["CDtot", "CD"]),
            "CDi": _last(vsp, result_id, ["CDi"]),
            "Cm": _last(vsp, result_id, ["CMytot", "CMy", "Cm"]),
        }
        for alpha, result_id in zip(alphas, result_ids)
    ]


def interpolate_alpha(points: list[dict], target_cl: float) -> tuple[float, float]:
    ordered = sorted(points, key=lambda row: row["CL"])
    if len(ordered) < 2:
        raise ValueError("At least two trim points are required")
    if target_cl <= ordered[0]["CL"]:
        left, right = ordered[0], ordered[1]
    elif target_cl >= ordered[-1]["CL"]:
        left, right = ordered[-2], ordered[-1]
    else:
        right_index = next(
            index for index, row in enumerate(ordered) if row["CL"] >= target_cl
        )
        left, right = ordered[right_index - 1], ordered[right_index]
    denominator = right["alpha_deg"] - left["alpha_deg"]
    slope = (right["CL"] - left["CL"]) / denominator
    if abs(slope) < 1.0e-10:
        raise RuntimeError("Near-zero lift-curve slope in fixed-CL trim")
    alpha = left["alpha_deg"] + (target_cl - left["CL"]) / slope
    return alpha, slope


def trim_to_cl(
    vsp,
    wing_id: str,
    target_cl: float,
    mach: float,
    native_reference: dict,
    analysis_config: dict,
    *,
    alpha_low: float = 0.0,
    alpha_high: float = 4.0,
    tolerance: float = 2.0e-5,
    max_corrections: int = 3,
) -> tuple[dict, list[dict], list[dict], int]:
    """Trim to fixed CL using one bracket sweep and correction solves."""
    trace = sweep_points(
        vsp,
        wing_id,
        [alpha_low, alpha_high],
        mach,
        native_reference,
        analysis_config,
    )
    alpha, slope = interpolate_alpha(trace, target_cl)
    execution_count = 1
    for _ in range(max_corrections + 1):
        final, raw_loads = evaluate(
            vsp,
            wing_id,
            alpha,
            mach,
            native_reference,
            analysis_config,
            loads=True,
        )
        execution_count += 1
        trace.append(final)
        if abs(final["CL"] - target_cl) <= tolerance:
            return final, raw_loads, trace, execution_count
        alpha += (target_cl - final["CL"]) / slope
    raise RuntimeError(
        f"Fixed-CL trim missed tolerance: target={target_cl:.8f}, "
        f"last={final['CL']:.8f}"
    )


def collapse_spanwise_loads(
    raw_rows: list[dict],
    flight_state: dict,
    scale_definition: dict,
    native_reference: dict,
    *,
    morph_eta_start: float,
    morph_eta_end: float,
    moment_axis_x_over_c: float = 0.25,
) -> list[dict]:
    """Convert VSPAERO native strip data into aircraft-scale SI loads."""
    q = float(flight_state["dynamic_pressure_Pa"])
    metres_per_model_unit = float(
        scale_definition["aircraft_m_per_model_unit"]
    )
    semi_span_native = 0.5 * float(
        native_reference["reference_span_model_units"]
    )
    bins: dict[float, list[dict]] = {}
    for row in raw_rows:
        y_native = abs(float(row.get("Yavg", 0.0)))
        bins.setdefault(round(y_native, 8), []).append(row)

    strips: list[dict] = []
    for y_native, items in sorted(bins.items()):
        def average(name: str) -> float:
            return sum(float(item.get(name, 0.0)) for item in items) / len(items)

        chord_native = average("Chord")
        dy_native = average("dSpan")
        y_m = y_native * metres_per_model_unit
        chord_m = chord_native * metres_per_model_unit
        dy_m = dy_native * metres_per_model_unit
        sectional_cl = average("cl")
        sectional_cd = average("cd")
        sectional_cdi = average("cdi")
        eta = y_native / semi_span_native
        lift_per_span = q * chord_m * sectional_cl
        drag_per_span = q * chord_m * sectional_cd
        induced_drag_per_span = q * chord_m * sectional_cdi
        pitching_coefficient = average("cmy")
        moment_per_span = q * chord_m**2 * (
            pitching_coefficient
            + (float(moment_axis_x_over_c) - 0.25) * sectional_cl
        )
        strips.append(
            {
                "eta": eta,
                "y_native": y_native,
                "y_m": y_m,
                "dy_native": dy_native,
                "dy_m": dy_m,
                "chord_native": chord_native,
                "chord_m": chord_m,
                "sectional_cl": sectional_cl,
                "sectional_cd": sectional_cd,
                "sectional_cdi": sectional_cdi,
                "lift_per_span_N_per_m": lift_per_span,
                "drag_per_span_N_per_m": drag_per_span,
                "induced_drag_per_span_N_per_m": induced_drag_per_span,
                "moment_proxy_Nm_per_m": moment_per_span,
                "morph_region": morph_eta_start <= eta <= morph_eta_end,
            }
        )
    return strips


def integrate_load_metrics(strips: list[dict]) -> dict:
    root_bending = sum(
        row["lift_per_span_N_per_m"] * row["dy_m"] * row["y_m"]
        for row in strips
    )
    half_wing_lift = sum(
        row["lift_per_span_N_per_m"] * row["dy_m"] for row in strips
    )
    morph_rows = [row for row in strips if row["morph_region"]]
    morph_lift = sum(
        row["lift_per_span_N_per_m"] * row["dy_m"] for row in morph_rows
    )
    morph_moment_proxy = sum(
        row["moment_proxy_Nm_per_m"] * row["dy_m"] for row in morph_rows
    )
    return {
        "half_wing_lift_N": half_wing_lift,
        "half_wing_root_bending_moment_Nm": root_bending,
        "morph_region_lift_N": morph_lift,
        "morph_region_moment_proxy_Nm": morph_moment_proxy,
    }

