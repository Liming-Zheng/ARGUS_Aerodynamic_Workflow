"""Geometry helpers for the segmented, zero-gap hinged-aileron model."""

from __future__ import annotations

from math import cos, radians, sin


def _parameter_value(vsp, geom_id: str, name: str, group: str, default=0.0):
    parameter_id = vsp.FindParm(geom_id, name, group)
    return vsp.GetParmVal(parameter_id) if parameter_id else default


def wing_section_rows(vsp, wing_id: str) -> tuple[str, list[dict]]:
    """Return section positions normalized by projected semi-span."""
    xsec_surface = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsec_surface)
    section_spans = [0.0]
    for index in range(1, count):
        section_spans.append(
            _parameter_value(
                vsp, wing_id, "ProjectedSpan", f"XSec_{index}", 0.0
            )
        )
    semi_span = sum(section_spans)
    y_native = 0.0
    rows = []
    for index, span in enumerate(section_spans):
        y_native += span
        xsec = vsp.GetXSec(xsec_surface, index)
        rows.append(
            {
                "section_id": index,
                "eta": y_native / semi_span if semi_span else 0.0,
                "y_native": y_native,
                "chord_native": vsp.GetXSecWidth(xsec),
                "xsec_shape_before": vsp.GetXSecShape(xsec),
            }
        )
    return xsec_surface, rows


def _surface_hinge_height(points, hinge_x: float) -> float:
    ordered = sorted(
        ((float(point.x()), float(point.y())) for point in points),
        key=lambda item: item[0],
    )
    for left, right in zip(ordered, ordered[1:]):
        if left[0] <= hinge_x <= right[0]:
            if abs(right[0] - left[0]) < 1.0e-12:
                return 0.5 * (left[1] + right[1])
            fraction = (hinge_x - left[0]) / (right[0] - left[0])
            return left[1] + fraction * (right[1] - left[1])
    return min(ordered, key=lambda item: abs(item[0] - hinge_x))[1]


def _rotate_surface(vsp, points, hinge_x: float, angle_deg: float):
    """Rotate the aft surface about its local skin point at the hinge.

    Using separate upper/lower skin hinge points gives a closed, zero-gap
    outer-mold-line approximation that is robust in OpenVSP. Positive command
    means trailing edge down.
    """
    hinge_y = _surface_hinge_height(points, hinge_x)
    theta = radians(-angle_deg)
    ctheta = cos(theta)
    stheta = sin(theta)
    output = vsp.Vec3dVec()
    for point in points:
        x = float(point.x())
        y = float(point.y())
        if x <= hinge_x:
            output.push_back(vsp.vec3d(x, y, float(point.z())))
            continue
        dx = x - hinge_x
        dy = y - hinge_y
        output.push_back(
            vsp.vec3d(
                hinge_x + dx * ctheta - dy * stheta,
                hinge_y + dx * stheta + dy * ctheta,
                float(point.z()),
            )
        )
    return output


def segment_for_eta(eta: float, segments: list[dict]) -> int | None:
    """Return the active segment index, assigning a shared boundary outboard."""
    for index, segment in enumerate(segments):
        start = float(segment["eta_start"])
        end = float(segment["eta_end"])
        if start - 1.0e-7 <= eta < end - 1.0e-7:
            return index
    if segments and abs(eta - float(segments[-1]["eta_end"])) <= 1.0e-7:
        return len(segments) - 1
    return None


def apply_segmented_hinged_ailerons(
    vsp,
    wing_id: str,
    segments: list[dict],
    deflections_deg: list[float],
    hinge_x_over_c: float,
) -> list[dict]:
    """Apply piecewise-constant rigid rotations to the NASA aileron segments."""
    if len(segments) != len(deflections_deg):
        raise ValueError("Each aileron segment requires one deflection")
    xsec_surface, rows = wing_section_rows(vsp, wing_id)
    output = []
    for row in rows:
        index = segment_for_eta(float(row["eta"]), segments)
        command = 0.0 if index is None else float(deflections_deg[index])
        shape_after = row["xsec_shape_before"]
        if abs(command) > 1.0e-12:
            xsec_before = vsp.GetXSec(xsec_surface, row["section_id"])
            upper_baseline = list(vsp.GetAirfoilUpperPnts(xsec_before))
            lower_baseline = list(vsp.GetAirfoilLowerPnts(xsec_before))
            vsp.ChangeXSecShape(
                xsec_surface, row["section_id"], vsp.XS_FILE_AIRFOIL
            )
            xsec_after = vsp.GetXSec(xsec_surface, row["section_id"])
            vsp.SetAirfoilPnts(
                xsec_after,
                _rotate_surface(
                    vsp, upper_baseline, hinge_x_over_c, command
                ),
                _rotate_surface(
                    vsp, lower_baseline, hinge_x_over_c, command
                ),
            )
            shape_after = vsp.GetXSecShape(xsec_after)
        output.append(
            {
                **row,
                "segment_index": "" if index is None else index,
                "segment_name": "" if index is None else segments[index]["name"],
                "deflection_deg": command,
                "hinge_x_over_c": hinge_x_over_c,
                "trailing_edge_displacement_over_c": (
                    -(1.0 - hinge_x_over_c) * sin(radians(command))
                ),
                "morphed": abs(command) > 1.0e-12,
                "xsec_shape_after": shape_after,
            }
        )
    return output

