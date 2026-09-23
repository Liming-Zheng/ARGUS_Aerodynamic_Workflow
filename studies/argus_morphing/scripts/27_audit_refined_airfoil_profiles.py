from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path


DEFAULT_OPENVSP = Path(r"<OPENVSP_ROOT>")


def parse_args():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
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


def parm(vsp, wing_id, name, group, default=0.0):
    parm_id = vsp.FindParm(wing_id, name, group)
    return vsp.GetParmVal(parm_id) if parm_id else default


def fingerprint(vsp, xsec):
    points = []
    for surface, values in (
        ("upper", vsp.GetAirfoilUpperPnts(xsec)),
        ("lower", vsp.GetAirfoilLowerPnts(xsec)),
    ):
        for point in values:
            points.append(
                f"{surface},{point.x():.10f},{point.y():.10f},{point.z():.10f}"
            )
    digest = hashlib.sha256("\n".join(points).encode("ascii")).hexdigest()
    return digest, len(points)


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    project = args.project.resolve()
    model = args.model or (
        project / "outputs" / "refined_baseline" / "baseline_wing_only_refined.vsp3"
    )
    output = project / "outputs" / "refined_baseline" / "airfoil_profile_audit"
    output.mkdir(parents=True, exist_ok=True)

    vsp = load_vsp(args.openvsp_root)
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(model))
    wing_id = vsp.FindGeom("cruise_wing", 0)
    if not wing_id:
        raise RuntimeError("Could not find cruise_wing")
    xsurf = vsp.GetXSecSurf(wing_id, 0)
    count = vsp.GetNumXSec(xsurf)
    semi_span = 0.5 * parm(vsp, wing_id, "TotalSpan", "WingGeom")
    y = 0.0
    rows = []
    for index in range(count):
        if index:
            y += parm(vsp, wing_id, "ProjectedSpan", f"XSec_{index}")
        xsec = vsp.GetXSec(xsurf, index)
        digest, point_count = fingerprint(vsp, xsec)
        rows.append({
            "section_id": index,
            "eta": y / semi_span if semi_span else 0.0,
            "airfoil_fingerprint": digest,
            "coordinate_count": point_count,
            "same_as_inboard": (
                index > 0 and digest == rows[index - 1]["airfoil_fingerprint"]
            ),
        })

    duplicate_pairs = [
        {
            "inboard_section": row["section_id"] - 1,
            "outboard_section": row["section_id"],
            "outboard_eta": row["eta"],
            "fingerprint": row["airfoil_fingerprint"],
        }
        for row in rows
        if row["same_as_inboard"]
    ]
    summary = {
        "model": str(model.resolve()),
        "section_count": count,
        "consecutive_identical_profile_pairs": len(duplicate_pairs),
        "status": (
            "review_required"
            if duplicate_pairs
            else "no_consecutive_duplicates_detected"
        ),
        "note": (
            "Identical neighboring coordinate arrays can indicate that "
            "SplitWingXSec inherited one bracket profile rather than blending."
        ),
    }
    write_csv(output / "refined_airfoil_profile_fingerprints.csv", rows)
    if duplicate_pairs:
        write_csv(
            output / "consecutive_identical_profile_pairs.csv",
            duplicate_pairs,
        )
    (output / "refined_airfoil_profile_audit.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()


