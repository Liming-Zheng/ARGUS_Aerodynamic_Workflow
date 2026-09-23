from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")
FT_TO_M = 0.3048


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--baseline-model", type=Path)
    parser.add_argument("--output-root", type=Path)
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for rel in ["python/openvsp", "python/openvsp_config", "python/degen_geom", "python/utilities"]:
        sys.path.insert(0, str(root / rel))
    import openvsp as vsp

    return vsp


def morph_offset(x: float, x_h: float, amplitude: float) -> float:
    if x <= x_h:
        return 0.0
    s = (x - x_h) / (1.0 - x_h)
    return -amplitude * (3.0 * s**2 - 2.0 * s**3)


def spanwise_amplitude(eta, eta_start, eta_end, amplitude_max, shape_type):
    if eta < eta_start or eta > eta_end:
        return 0.0
    r = (eta - eta_start) / (eta_end - eta_start)
    if shape_type == "uniform":
        factor = 1.0
    elif shape_type == "tip_increasing":
        factor = r
    elif shape_type == "tip_decreasing":
        factor = 1.0 - r
    elif shape_type == "bell":
        import math

        factor = math.sin(math.pi * r)
    else:
        raise ValueError(f"Unknown shape_type: {shape_type}")
    return amplitude_max * factor


def design_amplitude(eta, design):
    if design["shape_type"] != "control_points":
        return spanwise_amplitude(
            eta,
            design["eta_start"],
            design["eta_end"],
            design["A_max_over_c"],
            design["shape_type"],
        )
    if eta < design["eta_start"] or eta > design["eta_end"]:
        return 0.0
    control_etas = design["control_etas"]
    amplitudes = design["control_amplitudes_over_c"]
    if eta <= control_etas[0]:
        return amplitudes[0]
    if eta >= control_etas[-1]:
        return amplitudes[-1]
    for index in range(1, len(control_etas)):
        if eta <= control_etas[index]:
            fraction = (eta - control_etas[index - 1]) / (
                control_etas[index] - control_etas[index - 1]
            )
            return amplitudes[index - 1] + fraction * (
                amplitudes[index] - amplitudes[index - 1]
            )
    return amplitudes[-1]


def section_etas(vsp, wing_id):
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsurf)
    spans = [0.0]
    for index in range(1, count):
        parm_id = vsp.FindParm(wing_id, "ProjectedSpan", f"XSec_{index}")
        spans.append(vsp.GetParmVal(parm_id) if parm_id else 0.0)
    total = sum(spans)
    y = 0.0
    rows = []
    for index, span in enumerate(spans):
        y += span
        rows.append((index, y / total if total else 0.0, y))
    return xsurf, rows


def write_csv(path: Path, rows: list[dict]):
    fields = [
        "section_id",
        "eta",
        "y_native_ft",
        "y_m",
        "chord_native_ft",
        "chord_m",
        "x_h_over_c",
        "A_local_over_c",
        "TE_displacement_over_c",
        "TE_displacement_native_ft",
        "TE_displacement_m",
        "morphed",
        "shape_before",
        "shape_after",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate_case(vsp, baseline_model: Path, output_root: Path, design: dict):
    case_dir = output_root / design["case_id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(baseline_model))
    wing_id = vsp.FindGeom("cruise_wing", 0)
    if not wing_id:
        raise RuntimeError("Could not find cruise_wing in baseline model")
    xsurf, sections = section_etas(vsp, wing_id)
    schedule = []
    for section_id, eta, y in sections:
        xsec_before = vsp.GetXSec(xsurf, section_id)
        shape_before = vsp.GetXSecShape(xsec_before)
        chord = vsp.GetXSecWidth(xsec_before)
        amplitude = design_amplitude(eta, design)
        shape_after = shape_before
        if abs(amplitude) > 1.0e-12:
            upper_baseline = list(vsp.GetAirfoilUpperPnts(xsec_before))
            lower_baseline = list(vsp.GetAirfoilLowerPnts(xsec_before))
            vsp.ChangeXSecShape(xsurf, section_id, vsp.XS_FILE_AIRFOIL)
            xsec_after = vsp.GetXSec(xsurf, section_id)
            upper = vsp.Vec3dVec()
            lower = vsp.Vec3dVec()
            for point in upper_baseline:
                upper.push_back(
                    vsp.vec3d(
                        point.x(),
                        point.y() + morph_offset(point.x(), design["x_h_over_c"], amplitude),
                        point.z(),
                    )
                )
            for point in lower_baseline:
                lower.push_back(
                    vsp.vec3d(
                        point.x(),
                        point.y() + morph_offset(point.x(), design["x_h_over_c"], amplitude),
                        point.z(),
                    )
                )
            vsp.SetAirfoilPnts(xsec_after, upper, lower)
            shape_after = vsp.GetXSecShape(xsec_after)
        schedule.append({
            "section_id": section_id,
            "eta": eta,
            "y_native_ft": y,
            "y_m": y * FT_TO_M,
            "chord_native_ft": chord,
            "chord_m": chord * FT_TO_M,
            "x_h_over_c": design["x_h_over_c"],
            "A_local_over_c": amplitude,
            "TE_displacement_over_c": -amplitude,
            "TE_displacement_native_ft": -amplitude * chord,
            "TE_displacement_m": -amplitude * chord * FT_TO_M,
            "morphed": abs(amplitude) > 1.0e-12,
            "shape_before": shape_before,
            "shape_after": shape_after,
        })
    vsp.Update()
    model_path = case_dir / f"{design['case_id']}.vsp3"
    vsp.SetVSP3FileName(str(model_path))
    vsp.WriteVSPFile(str(model_path), vsp.SET_ALL)
    (case_dir / f"{design['case_id']}_design.json").write_text(
        json.dumps(design, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(case_dir / f"{design['case_id']}_section_schedule.csv", schedule)
    return model_path, schedule


def main():
    args = parse_args()
    baseline_model = args.baseline_model
    if baseline_model is None:
        refined = (
            args.project
            / "outputs"
            / "refined_baseline"
            / "baseline_wing_only_refined.vsp3"
        )
        baseline_model = refined if refined.exists() else (
            args.project / "outputs" / "baseline" / "baseline_wing_only.vsp3"
        )
    cases_path = args.cases or args.project / "config" / "representative_cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    output_root = args.output_root or args.project / "outputs" / "refined_cases"
    output_root.mkdir(parents=True, exist_ok=True)
    vsp = load_vsp(args.openvsp_root)
    manifest = []
    for design in cases:
        model_path, schedule = generate_case(vsp, baseline_model, output_root, design)
        manifest.append({
            "case_id": design["case_id"],
            "model": str(model_path),
            "morphed_sections": sum(bool(row["morphed"]) for row in schedule),
            "max_abs_TE_displacement_m": max(
                abs(row["TE_displacement_m"]) for row in schedule
            ),
        })
        print(f"Generated {design['case_id']}: {model_path}")
    with (output_root / "representative_case_manifest.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)


if __name__ == "__main__":
    main()


