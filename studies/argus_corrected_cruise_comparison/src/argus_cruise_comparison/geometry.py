"""Geometry construction helpers shared by both morphing concepts."""

from __future__ import annotations

from .parameterization import MorphingSchedule


def trailing_edge_offset(
    x_over_c: float,
    start_x_over_c: float,
    amplitude_over_c: float,
) -> float:
    """Return the normalized smoothstep camber-line displacement."""
    if x_over_c <= start_x_over_c:
        return 0.0
    xi = (x_over_c - start_x_over_c) / (1.0 - start_x_over_c)
    return -amplitude_over_c * (3.0 * xi**2 - 2.0 * xi**3)


def _parameter_value(vsp, geom_id: str, name: str, group: str, default=0.0):
    parameter_id = vsp.FindParm(geom_id, name, group)
    return vsp.GetParmVal(parameter_id) if parameter_id else default


def wing_section_rows(vsp, wing_id: str) -> tuple[str, list[dict]]:
    """Return OpenVSP section positions normalized by projected semi-span."""
    xsec_surface = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsec_surface)
    section_spans = [0.0]
    for index in range(1, count):
        section_spans.append(
            _parameter_value(
                vsp,
                wing_id,
                "ProjectedSpan",
                f"XSec_{index}",
                0.0,
            )
        )
    semi_span = sum(section_spans)
    y_native = 0.0
    rows: list[dict] = []
    for index, span in enumerate(section_spans):
        y_native += span
        xsec = vsp.GetXSec(xsec_surface, index)
        rows.append(
            {
                "section_id": index,
                "eta": y_native / semi_span if semi_span else 0.0,
                "y_native": y_native,
                "chord_native": vsp.GetXSecWidth(xsec),
                "baseline_twist_deg": _parameter_value(
                    vsp,
                    wing_id,
                    "Twist",
                    f"XSec_{index}",
                    0.0,
                ),
                "baseline_twist_location_x_over_c": _parameter_value(
                    vsp,
                    wing_id,
                    "Twist_Location",
                    f"XSec_{index}",
                    0.25,
                ),
                "xsec_shape_before": vsp.GetXSecShape(xsec),
            }
        )
    return xsec_surface, rows


def apply_trailing_edge_morphing(
    vsp,
    wing_id: str,
    schedule: MorphingSchedule,
    start_x_over_c: float,
) -> list[dict]:
    xsec_surface, rows = wing_section_rows(vsp, wing_id)
    output: list[dict] = []
    for row in rows:
        section_id = row["section_id"]
        xsec_before = vsp.GetXSec(xsec_surface, section_id)
        amplitude = schedule.value(row["eta"])
        shape_after = row["xsec_shape_before"]
        if abs(amplitude) > 1.0e-12:
            upper_baseline = list(vsp.GetAirfoilUpperPnts(xsec_before))
            lower_baseline = list(vsp.GetAirfoilLowerPnts(xsec_before))
            vsp.ChangeXSecShape(xsec_surface, section_id, vsp.XS_FILE_AIRFOIL)
            xsec_after = vsp.GetXSec(xsec_surface, section_id)
            upper = vsp.Vec3dVec()
            lower = vsp.Vec3dVec()
            for point in upper_baseline:
                upper.push_back(
                    vsp.vec3d(
                        point.x(),
                        point.y()
                        + trailing_edge_offset(
                            point.x(), start_x_over_c, amplitude
                        ),
                        point.z(),
                    )
                )
            for point in lower_baseline:
                lower.push_back(
                    vsp.vec3d(
                        point.x(),
                        point.y()
                        + trailing_edge_offset(
                            point.x(), start_x_over_c, amplitude
                        ),
                        point.z(),
                    )
                )
            vsp.SetAirfoilPnts(xsec_after, upper, lower)
            shape_after = vsp.GetXSecShape(xsec_after)
        output.append(
            {
                **row,
                "command_over_c": amplitude,
                "trailing_edge_displacement_over_c": -amplitude,
                "trailing_edge_displacement_native": (
                    -amplitude * row["chord_native"]
                ),
                "x_h_over_c": start_x_over_c,
                "morphed": abs(amplitude) > 1.0e-12,
                "xsec_shape_after": shape_after,
            }
        )
    return output


def apply_twist_morphing(
    vsp,
    wing_id: str,
    schedule: MorphingSchedule,
    rotation_axis_x_over_c: float,
) -> list[dict]:
    _, rows = wing_section_rows(vsp, wing_id)
    output: list[dict] = []
    for row in rows:
        section_id = row["section_id"]
        increment = schedule.value(row["eta"])
        final_twist = row["baseline_twist_deg"] + increment
        twist_id = vsp.FindParm(wing_id, "Twist", f"XSec_{section_id}")
        location_id = vsp.FindParm(
            wing_id, "Twist_Location", f"XSec_{section_id}"
        )
        if twist_id:
            vsp.SetParmVal(twist_id, final_twist)
        if location_id and row["eta"] > schedule.eta_start:
            vsp.SetParmVal(location_id, rotation_axis_x_over_c)
        output.append(
            {
                **row,
                "incremental_twist_deg": increment,
                "final_twist_deg": final_twist,
                "rotation_axis_x_over_c": rotation_axis_x_over_c,
                "morphed": abs(increment) > 1.0e-12,
            }
        )
    return output

