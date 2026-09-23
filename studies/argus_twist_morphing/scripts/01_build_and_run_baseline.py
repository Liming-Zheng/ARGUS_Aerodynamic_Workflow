from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for rel in ["python/openvsp", "python/openvsp_config", "python/degen_geom", "python/utilities"]:
        sys.path.insert(0, str(root / rel))
    import openvsp as vsp

    return vsp


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def parm(vsp, geom_id: str, name: str, group: str, default=""):
    parm_id = vsp.FindParm(geom_id, name, group)
    return vsp.GetParmVal(parm_id) if parm_id else default


def clear_to_wing(vsp, wing_name: str) -> str:
    wing = vsp.FindGeom(wing_name, 0)
    if not wing:
        raise RuntimeError(f"Could not find geometry named {wing_name!r}")
    keep = {wing}
    parent = vsp.GetGeomParent(wing)
    while parent and parent != "NONE":
        keep.add(parent)
        next_parent = vsp.GetGeomParent(parent)
        if not next_parent or next_parent == parent or next_parent == "NONE":
            break
        parent = next_parent

    def depth(geom_id: str) -> int:
        result = 0
        parent_id = vsp.GetGeomParent(geom_id)
        while parent_id and parent_id != "NONE":
            result += 1
            next_parent = vsp.GetGeomParent(parent_id)
            if not next_parent or next_parent == parent_id:
                break
            parent_id = next_parent
        return result

    for geom_id in sorted(list(vsp.FindGeoms()), key=depth, reverse=True):
        if geom_id not in keep:
            vsp.DeleteGeom(geom_id)
    vsp.Update()
    return vsp.FindGeom(wing_name, 0)


def geometry_rows(vsp, wing_id: str, source_model: Path):
    span = parm(vsp, wing_id, "TotalSpan", "WingGeom")
    area = parm(vsp, wing_id, "TotalArea", "WingGeom")
    aspect = parm(vsp, wing_id, "TotalAR", "WingGeom")
    mac = parm(vsp, wing_id, "MAC", "WingGeom")
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsurf)
    root_chord = vsp.GetXSecWidth(vsp.GetXSec(xsurf, 0))
    tip_chord = vsp.GetXSecWidth(vsp.GetXSec(xsurf, count - 1))
    taper = tip_chord / root_chord
    summary = [
        {"parameter": "span_full", "value": span, "unit": "m", "notes": "OpenVSP TotalSpan"},
        {"parameter": "span_half", "value": span / 2.0, "unit": "m", "notes": "One aerodynamic half-wing"},
        {"parameter": "reference_area", "value": area, "unit": "m^2", "notes": "OpenVSP TotalArea"},
        {"parameter": "aspect_ratio", "value": aspect, "unit": "-", "notes": "OpenVSP TotalAR"},
        {"parameter": "taper_ratio", "value": taper, "unit": "-", "notes": "tip chord / root chord"},
        {"parameter": "mean_aerodynamic_chord", "value": mac, "unit": "m", "notes": "OpenVSP MAC"},
        {"parameter": "root_chord", "value": root_chord, "unit": "m", "notes": ""},
        {"parameter": "tip_chord", "value": tip_chord, "unit": "m", "notes": ""},
        {"parameter": "sweep_quarter_chord", "value": parm(vsp, wing_id, "Sweep", "XSec_1"), "unit": "deg", "notes": "Section sweep; Sec_Sweep_Location=0.25"},
        {"parameter": "dihedral", "value": parm(vsp, wing_id, "Dihedral", "XSec_1"), "unit": "deg", "notes": "First section"},
        {"parameter": "model_source", "value": str(source_model), "unit": "-", "notes": "NASA public OpenVSP model"},
        {"parameter": "wing_only_or_full_aircraft", "value": "wing-only", "unit": "-", "notes": "cruise_wing and required parent container retained"},
    ]

    section_rows = []
    airfoil_rows = []
    y_le = 0.0
    x_le = 0.0
    z_le = 0.0
    semi_span = span / 2.0
    for index in range(count):
        xsec = vsp.GetXSec(xsurf, index)
        chord = vsp.GetXSecWidth(xsec)
        twist = parm(vsp, wing_id, "Twist", f"XSec_{index}", 0.0)
        sweep = parm(vsp, wing_id, "Sweep", f"XSec_{index}", 0.0)
        dihedral = parm(vsp, wing_id, "Dihedral", f"XSec_{index}", 0.0)
        if index > 0:
            span_i = parm(vsp, wing_id, "ProjectedSpan", f"XSec_{index}", 0.0)
            previous_chord = section_rows[-1]["chord"]
            sweep_location = parm(vsp, wing_id, "Sec_Sweep_Location", f"XSec_{index}", 0.25)
            x_le += span_i * math.tan(math.radians(sweep)) + sweep_location * (previous_chord - chord)
            y_le += span_i
            z_le += span_i * math.tan(math.radians(dihedral))
        section_rows.append({
            "section_id": index,
            "eta": y_le / semi_span,
            "y": y_le,
            "chord": chord,
            "twist": twist,
            "sweep": sweep,
            "dihedral": dihedral,
            "x_le": x_le,
            "y_le": y_le,
            "z_le": z_le,
            "airfoil_source": "NASA file airfoil",
            "notes": "Wing-local coordinates before global XForm rotations/translations",
        })
        try:
            upper = list(vsp.GetAirfoilUpperPnts(xsec))
            lower = list(vsp.GetAirfoilLowerPnts(xsec))
            for surface, points in [("upper", upper), ("lower", lower)]:
                for point_index, point in enumerate(points):
                    airfoil_rows.append({
                        "section_id": index,
                        "eta": y_le / semi_span,
                        "surface": surface,
                        "point_index": point_index,
                        "x_over_c": point.x(),
                        "z_over_c": point.y(),
                    })
        except Exception:
            pass
    return summary, section_rows, airfoil_rows


def set_int(vsp, analysis, name, value):
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetIntAnalysisInput(analysis, name, [int(value)], 0)


def set_double(vsp, analysis, name, value):
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetDoubleAnalysisInput(analysis, name, [float(value)], 0)


def set_string(vsp, analysis, name, value):
    if name in set(vsp.GetAnalysisInputNames(analysis)):
        vsp.SetStringAnalysisInput(analysis, name, [str(value)], 0)


def doubles(vsp, result_id, name):
    try:
        return list(vsp.GetDoubleResults(result_id, name))
    except Exception:
        return []


def last(vsp, result_id, names):
    for name in names:
        values = doubles(vsp, result_id, name)
        if values:
            return values[-1]
    return ""


def run_vspaero(vsp, wing_id: str, config: dict, raw_dir: Path):
    compute = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(compute)
    set_int(vsp, compute, "AnalysisMethod", config["analysis_method"])
    set_int(vsp, compute, "GeomSet", vsp.SET_NONE)
    set_int(vsp, compute, "ThinGeomSet", vsp.SET_ALL)
    vsp.ExecAnalysis(compute)

    coefficient_rows = []
    load_rows = []
    for alpha in config["alphas_deg"]:
        analysis = "VSPAEROSweep"
        vsp.SetAnalysisInputDefaults(analysis)
        set_int(vsp, analysis, "AnalysisMethod", config["analysis_method"])
        set_int(vsp, analysis, "GeomSet", vsp.SET_ALL)
        set_int(vsp, analysis, "RefFlag", 0)
        set_double(vsp, analysis, "Sref", config["reference_area_m2"])
        set_double(vsp, analysis, "cref", config["reference_chord_m"])
        set_double(vsp, analysis, "bref", config["reference_span_m"])
        set_string(vsp, analysis, "WingID", wing_id)
        set_double(vsp, analysis, "AlphaStart", alpha)
        set_double(vsp, analysis, "AlphaEnd", alpha)
        set_int(vsp, analysis, "AlphaNpts", 1)
        set_double(vsp, analysis, "BetaStart", config["beta_deg"])
        set_double(vsp, analysis, "BetaEnd", config["beta_deg"])
        set_int(vsp, analysis, "BetaNpts", 1)
        set_double(vsp, analysis, "MachStart", config["mach"])
        set_double(vsp, analysis, "MachEnd", config["mach"])
        set_int(vsp, analysis, "MachNpts", 1)
        set_int(vsp, analysis, "WakeNumIter", config["wake_iterations"])
        vsp.ExecAnalysis(analysis)
        history_id = vsp.FindLatestResultsID("VSPAERO_History")
        load_id = vsp.FindLatestResultsID("VSPAERO_Load")
        case_id = f"baseline_a{alpha:+05.1f}".replace("+", "p").replace("-", "m")
        coefficient_rows.append({
            "case_id": case_id,
            "alpha_deg": alpha,
            "beta_deg": config["beta_deg"],
            "mach": config["mach"],
            "reynolds": "",
            "CL": last(vsp, history_id, ["CLtot", "CL"]),
            "CD": last(vsp, history_id, ["CDtot", "CD"]),
            "CDi": last(vsp, history_id, ["CDi"]),
            "CDp": last(vsp, history_id, ["CDo", "CDp"]),
            "Cm": last(vsp, history_id, ["CMytot", "CMy", "Cm"]),
            "Cl": last(vsp, history_id, ["CMxtot", "CMx", "Cl"]),
            "Cn": last(vsp, history_id, ["CMztot", "CMz", "Cn"]),
            "notes": "VLM wing-only; Reynolds not explicitly configured",
        })
        names = list(vsp.GetAllDataNames(load_id))
        columns = {name: doubles(vsp, load_id, name) for name in names}
        row_count = max((len(values) for values in columns.values()), default=0)
        for index in range(row_count):
            row = {"case_id": case_id, "alpha_deg": alpha, "station_index": index}
            for name, values in columns.items():
                if index < len(values):
                    row[name] = values[index]
            load_rows.append(row)

    write_csv(
        raw_dir / "baseline_vspaero_coefficients.csv",
        coefficient_rows,
        ["case_id", "alpha_deg", "beta_deg", "mach", "reynolds", "CL", "CD", "CDi", "CDp", "Cm", "Cl", "Cn", "notes"],
    )
    fields = ["case_id", "alpha_deg", "station_index"] + sorted(
        set().union(*(row.keys() for row in load_rows)) - {"case_id", "alpha_deg", "station_index"}
    )
    write_csv(raw_dir / "baseline_vspaero_load_raw.csv", load_rows, fields)


def main():
    args = parse_args()
    config = json.loads((args.project / "config" / "baseline_config.json").read_text(encoding="utf-8"))
    output = args.project / "outputs" / "baseline"
    raw = output / "raw"
    output.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    source = Path(config["source_model"])
    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(source))
    wing = clear_to_wing(vsp, config["wing_name"])
    baseline_model = output / "baseline_wing_only.vsp3"
    vsp.SetVSP3FileName(str(baseline_model))
    vsp.WriteVSPFile(str(baseline_model), vsp.SET_ALL)
    summary, sections, airfoils = geometry_rows(vsp, wing, source)
    write_csv(output / "baseline_geometry_summary.csv", summary, ["parameter", "value", "unit", "notes"])
    write_csv(output / "baseline_section_table.csv", sections, ["section_id", "eta", "y", "chord", "twist", "sweep", "dihedral", "x_le", "y_le", "z_le", "airfoil_source", "notes"])
    write_csv(raw / "baseline_airfoil_points.csv", airfoils, ["section_id", "eta", "surface", "point_index", "x_over_c", "z_over_c"])
    run_vspaero(vsp, wing, config, raw)
    print(f"Baseline OpenVSP/VSPAERO outputs written to {output}")


if __name__ == "__main__":
    main()


