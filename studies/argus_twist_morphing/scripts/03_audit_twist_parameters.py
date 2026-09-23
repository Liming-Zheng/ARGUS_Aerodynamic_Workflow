from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Audit section twist parameters before modifying geometry."
    )
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--openvsp-root", type=Path, default=DEFAULT_OPENVSP)
    parser.add_argument("--model", type=Path)
    return parser.parse_args()


def load_vsp(root: Path):
    os.add_dll_directory(str(root))
    os.add_dll_directory(str(root / "python" / "openvsp" / "openvsp"))
    for rel in [
        "python/openvsp",
        "python/openvsp_config",
        "python/degen_geom",
        "python/utilities",
    ]:
        sys.path.insert(0, str(root / rel))
    import openvsp as vsp

    return vsp


def parameter_value(vsp, geom_id: str, name: str, group: str):
    parm_id = vsp.FindParm(geom_id, name, group)
    if not parm_id:
        return "", ""
    return parm_id, vsp.GetParmVal(parm_id)


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    config = json.loads(
        (args.project / "config" / "baseline_config.json").read_text(
            encoding="utf-8"
        )
    )
    model = args.model or Path(config["source_model"])
    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(model))

    wing_id = vsp.FindGeom(config["wing_name"], 0)
    if not wing_id:
        raise RuntimeError(f"Could not find wing {config['wing_name']!r}")

    xsurf = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsurf)
    spans = [0.0]
    for index in range(1, count):
        _, span = parameter_value(vsp, wing_id, "ProjectedSpan", f"XSec_{index}")
        spans.append(float(span or 0.0))
    semi_span = sum(spans)

    rows = []
    y = 0.0
    for index, span in enumerate(spans):
        y += span
        group = f"XSec_{index}"
        twist_id, twist = parameter_value(vsp, wing_id, "Twist", group)
        location_id, location = parameter_value(
            vsp, wing_id, "Twist_Location", group
        )
        if not location_id:
            location_id, location = parameter_value(
                vsp, wing_id, "Twist_Location", "WingGeom"
            )
        xsec = vsp.GetXSec(xsurf, index)
        rows.append(
            {
                "section_id": index,
                "eta": y / semi_span if semi_span else 0.0,
                "y": y,
                "chord": vsp.GetXSecWidth(xsec),
                "twist_deg": twist,
                "twist_parm_id": twist_id,
                "twist_location_x_over_c": location,
                "twist_location_parm_id": location_id,
                "xsec_shape": vsp.GetXSecShape(xsec),
            }
        )

    output = args.project / "outputs" / "twist_parameter_audit"
    write_csv(output / "section_twist_parameter_audit.csv", rows)
    summary = {
        "model": str(model),
        "wing_name": config["wing_name"],
        "section_count": count,
        "twist_parameter_available": all(bool(row["twist_parm_id"]) for row in rows),
        "twist_location_parameter_found": any(
            bool(row["twist_location_parm_id"]) for row in rows
        ),
        "requested_rotation_axis_x_over_c": 0.25,
        "note": (
            "If no Twist_Location parameter is exposed, geometry movement must "
            "be verified from exported section coordinates before optimization."
        ),
    }
    (output / "twist_parameter_audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"Wrote audit table to {output}")


if __name__ == "__main__":
    main()


