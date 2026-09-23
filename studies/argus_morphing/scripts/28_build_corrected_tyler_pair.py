from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")
DEFAULT_OUTPUT = PROJECT / "outputs" / "tyler_validation_2026_07_29"
FT_TO_M = 0.3048

sys.path.insert(0, str(PROJECT / "src"))

from argus_morphing.airfoil_refinement import (  # noqa: E402
    blend_profiles,
    bracket_indices,
    cosine_grid,
    interpolate_surface,
    max_profile_difference,
)
from argus_morphing.morphing_shapes import control_point_amplitude  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--eta-start", type=float, default=0.55)
    parser.add_argument("--eta-end", type=float, default=0.95)
    parser.add_argument("--max-segment-eta", type=float, default=0.05)
    parser.add_argument("--point-count", type=int, default=161)
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for relative in [
        "python/openvsp",
        "python/openvsp_config",
        "python/degen_geom",
        "python/utilities",
    ]:
        sys.path.insert(0, str(root / relative))
    import openvsp as vsp

    return vsp


def parm(vsp, wing_id, name, group, default=0.0):
    parm_id = vsp.FindParm(wing_id, name, group)
    return vsp.GetParmVal(parm_id) if parm_id else default


def section_rows(vsp, wing_id):
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsurf)
    semi_span = parm(vsp, wing_id, "TotalSpan", "WingGeom") / 2.0
    y_value = 0.0
    rows = []
    for index in range(count):
        span = parm(vsp, wing_id, "ProjectedSpan", f"XSec_{index}") if index else 0.0
        y_start = y_value
        y_value += span
        rows.append(
            {
                "section_id": index,
                "eta_start": y_start / semi_span,
                "eta_end": y_value / semi_span,
                "segment_eta": span / semi_span,
                "y_native_ft": y_value,
                "chord_native_ft": vsp.GetXSecWidth(vsp.GetXSec(xsurf, index)),
                "twist_deg": parm(vsp, wing_id, "Twist", f"XSec_{index}"),
            }
        )
    return rows


def profile_from_xsec(vsp, xsec):
    def points(values):
        return [(point.x(), point.y()) for point in values]

    return points(vsp.GetAirfoilUpperPnts(xsec)), points(vsp.GetAirfoilLowerPnts(xsec))


def capture_original_profiles(vsp, wing_id):
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    rows = section_rows(vsp, wing_id)
    return [
        {
            **row,
            "profile": profile_from_xsec(vsp, vsp.GetXSec(xsurf, row["section_id"])),
        }
        for row in rows
    ]


def intersects(row, eta_start, eta_end):
    return row["eta_end"] > eta_start and row["eta_start"] < eta_end


def refine(vsp, wing_id, eta_start, eta_end, max_segment_eta):
    split_count = 0
    while True:
        rows = section_rows(vsp, wing_id)
        candidate = next(
            (
                row
                for row in rows[1:]
                if intersects(row, eta_start, eta_end)
                and row["segment_eta"] > max_segment_eta + 1.0e-10
            ),
            None,
        )
        if candidate is None:
            return split_count
        vsp.SplitWingXSec(wing_id, candidate["section_id"])
        vsp.Update()
        split_count += 1


def restore_twist(vsp, wing_id, original):
    original_etas = [row["eta_end"] for row in original]
    original_twists = [row["twist_deg"] for row in original]
    for row in section_rows(vsp, wing_id):
        left, right, fraction = bracket_indices(original_etas, row["eta_end"])
        twist = original_twists[left]
        if left != right:
            twist += fraction * (original_twists[right] - original_twists[left])
        parm_id = vsp.FindParm(wing_id, "Twist", f"XSec_{row['section_id']}")
        if parm_id:
            vsp.SetParmVal(parm_id, twist)
    vsp.Update()


def to_vec(vsp, surface):
    values = vsp.Vec3dVec()
    for x_value, z_value in surface:
        values.push_back(vsp.vec3d(x_value, z_value, 0.0))
    return values


def resample_profile(profile, x_grid):
    return (
        list(zip(x_grid, interpolate_surface(profile[0], x_grid))),
        list(zip(x_grid, interpolate_surface(profile[1], x_grid))),
    )


def correct_inserted_profiles(vsp, wing_id, original, point_count):
    original_etas = [row["eta_end"] for row in original]
    original_profiles = [row["profile"] for row in original]
    x_grid = cosine_grid(point_count)
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    audit = []
    for row in section_rows(vsp, wing_id):
        left, right, fraction = bracket_indices(original_etas, row["eta_end"])
        is_original = left == right
        if is_original:
            audit.append(
                {
                    "section_id": row["section_id"],
                    "eta": row["eta_end"],
                    "section_kind": "original",
                    "inboard_original_eta": original_etas[left],
                    "outboard_original_eta": original_etas[right],
                    "blend_fraction": 0.0,
                    "max_coordinate_error": 0.0,
                }
            )
            continue
        expected = blend_profiles(
            original_profiles[left],
            original_profiles[right],
            fraction,
            x_grid,
        )
        vsp.ChangeXSecShape(xsurf, row["section_id"], vsp.XS_FILE_AIRFOIL)
        xsec = vsp.GetXSec(xsurf, row["section_id"])
        vsp.SetAirfoilPnts(
            xsec,
            to_vec(vsp, expected[0]),
            to_vec(vsp, expected[1]),
        )
        actual = resample_profile(profile_from_xsec(vsp, xsec), x_grid)
        audit.append(
            {
                "section_id": row["section_id"],
                "eta": row["eta_end"],
                "section_kind": "inserted_blended",
                "inboard_original_eta": original_etas[left],
                "outboard_original_eta": original_etas[right],
                "blend_fraction": fraction,
                "max_coordinate_error": max_profile_difference(expected, actual),
            }
        )
    vsp.Update()
    return audit


def morph_offset(x_value, x_h, amplitude):
    if x_value <= x_h:
        return 0.0
    xi = (x_value - x_h) / (1.0 - x_h)
    return -amplitude * (3.0 * xi**2 - 2.0 * xi**3)


def design_amplitude(eta, design):
    return control_point_amplitude(
        eta,
        float(design["eta_start"]),
        float(design["eta_end"]),
        design["control_etas"],
        design["control_amplitudes_over_c"],
    )


def apply_morphing(vsp, wing_id, design):
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    schedule = []
    for row in section_rows(vsp, wing_id):
        section_id = row["section_id"]
        eta = row["eta_end"]
        amplitude = design_amplitude(eta, design)
        xsec_before = vsp.GetXSec(xsurf, section_id)
        baseline_profile = profile_from_xsec(vsp, xsec_before)
        if abs(amplitude) > 1.0e-12:
            upper = [
                (x_value, z_value + morph_offset(x_value, design["x_h_over_c"], amplitude))
                for x_value, z_value in baseline_profile[0]
            ]
            lower = [
                (x_value, z_value + morph_offset(x_value, design["x_h_over_c"], amplitude))
                for x_value, z_value in baseline_profile[1]
            ]
            vsp.ChangeXSecShape(xsurf, section_id, vsp.XS_FILE_AIRFOIL)
            xsec_after = vsp.GetXSec(xsurf, section_id)
            vsp.SetAirfoilPnts(xsec_after, to_vec(vsp, upper), to_vec(vsp, lower))
        schedule.append(
            {
                "section_id": section_id,
                "eta": eta,
                "y_native_ft": row["y_native_ft"],
                "y_m": row["y_native_ft"] * FT_TO_M,
                "chord_native_ft": row["chord_native_ft"],
                "chord_m": row["chord_native_ft"] * FT_TO_M,
                "x_h_over_c": design["x_h_over_c"],
                "A_local_over_c": amplitude,
                "TE_displacement_over_c": -amplitude,
                "TE_displacement_native_ft": -amplitude * row["chord_native_ft"],
                "TE_displacement_m": -amplitude * row["chord_native_ft"] * FT_TO_M,
                "morphed": abs(amplitude) > 1.0e-12,
            }
        )
    vsp.Update()
    return schedule


def fingerprint_model(vsp, wing_id):
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    rows = []
    previous = None
    for row in section_rows(vsp, wing_id):
        xsec = vsp.GetXSec(xsurf, row["section_id"])
        text = []
        for label, values in (
            ("upper", vsp.GetAirfoilUpperPnts(xsec)),
            ("lower", vsp.GetAirfoilLowerPnts(xsec)),
        ):
            text.extend(
                f"{label},{point.x():.12f},{point.y():.12f},{point.z():.12f}"
                for point in values
            )
        digest = hashlib.sha256("\n".join(text).encode("ascii")).hexdigest()
        rows.append(
            {
                "section_id": row["section_id"],
                "eta": row["eta_end"],
                "coordinate_count": len(text),
                "sha256": digest,
                "same_as_inboard": digest == previous if previous else False,
            }
        )
        previous = digest
    return rows


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def save_model(vsp, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    vsp.SetVSP3FileName(str(path))
    vsp.WriteVSPFile(str(path), vsp.SET_ALL)


def main():
    args = parse_args()
    project = args.project.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((project / "config" / "baseline_config.json").read_text(encoding="utf-8"))
    source_design = json.loads(
        (
            project
            / "outputs"
            / "optimization"
            / "samples"
            / "mcv2_i002_c01"
            / "mcv2_i002_c01_design.json"
        ).read_text(encoding="utf-8")
    )
    source = project / "outputs" / "baseline" / "baseline_wing_only.vsp3"

    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(source))
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    original = capture_original_profiles(vsp, wing_id)
    geometry_before = {
        "span_native_ft": parm(vsp, wing_id, "TotalSpan", "WingGeom"),
        "area_native_ft2": parm(vsp, wing_id, "TotalArea", "WingGeom"),
        "mac_native_ft": parm(vsp, wing_id, "MAC", "WingGeom"),
        "aspect_ratio": parm(vsp, wing_id, "TotalAR", "WingGeom"),
        "section_count": len(original),
    }
    split_count = refine(
        vsp,
        wing_id,
        args.eta_start,
        args.eta_end,
        args.max_segment_eta,
    )
    restore_twist(vsp, wing_id, original)
    interpolation_audit = correct_inserted_profiles(vsp, wing_id, original, args.point_count)
    geometry_after = {
        "span_native_ft": parm(vsp, wing_id, "TotalSpan", "WingGeom"),
        "area_native_ft2": parm(vsp, wing_id, "TotalArea", "WingGeom"),
        "mac_native_ft": parm(vsp, wing_id, "MAC", "WingGeom"),
        "aspect_ratio": parm(vsp, wing_id, "TotalAR", "WingGeom"),
        "section_count": len(section_rows(vsp, wing_id)),
    }

    baseline_dir = output / "baseline_corrected"
    baseline_model = baseline_dir / "baseline_corrected.vsp3"
    save_model(vsp, baseline_model)
    baseline_design = {
        "case_id": "baseline_corrected",
        "eta_start": 0.6,
        "eta_end": 1.0,
        "x_h_over_c": 0.62,
        "A_max_over_c": 0.0,
        "shape_type": "control_points",
        "control_etas": source_design["control_etas"],
        "control_amplitudes_over_c": [0.0] * len(source_design["control_etas"]),
        "max_adjacent_delta": 0.0,
        "max_spanwise_slope": 0.0,
        "alpha_deg": 2.0,
        "mach": 0.1,
        "notes": "Corrected matched baseline for Tyler RANS validation.",
    }
    write_json(baseline_dir / "baseline_corrected_design.json", baseline_design)
    write_csv(baseline_dir / "baseline_corrected_section_table.csv", section_rows(vsp, wing_id))
    write_csv(baseline_dir / "baseline_corrected_airfoil_fingerprints.csv", fingerprint_model(vsp, wing_id))

    candidate_dir = output / "mcv2_i002_c01"
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(baseline_model))
    wing_id = vsp.FindGeom(config["wing_name"], 0)
    schedule = apply_morphing(vsp, wing_id, source_design)
    candidate_model = candidate_dir / "mcv2_i002_c01.vsp3"
    save_model(vsp, candidate_model)
    write_json(candidate_dir / "mcv2_i002_c01_design.json", source_design)
    write_csv(candidate_dir / "mcv2_i002_c01_section_schedule.csv", schedule)
    write_csv(candidate_dir / "mcv2_i002_c01_airfoil_fingerprints.csv", fingerprint_model(vsp, wing_id))

    max_error = max(
        row["max_coordinate_error"]
        for row in interpolation_audit
        if row["section_kind"] == "inserted_blended"
    )
    geometry_differences = {
        name: geometry_after[name] - geometry_before[name]
        for name in geometry_before
        if name != "section_count"
    }
    audit_summary = {
        "source_model": str(source),
        "candidate_source_design": "mcv2_i002_c01",
        "method": "Only SplitWingXSec-inserted profiles are linearly blended between original bracketing airfoils on a cosine x/c grid.",
        "point_count_per_surface": args.point_count,
        "split_count": split_count,
        "original_section_count": geometry_before["section_count"],
        "corrected_section_count": geometry_after["section_count"],
        "maximum_inserted_profile_coordinate_error": max_error,
        "geometry_differences_excluding_section_count": geometry_differences,
        "baseline_and_candidate_share_corrected_base": True,
    }
    write_csv(output / "airfoil_interpolation_audit.csv", interpolation_audit)
    write_json(output / "airfoil_interpolation_audit.json", audit_summary)
    print(json.dumps(audit_summary, indent=2))
    print(f"Wrote matched pair to {output}")


if __name__ == "__main__":
    main()


