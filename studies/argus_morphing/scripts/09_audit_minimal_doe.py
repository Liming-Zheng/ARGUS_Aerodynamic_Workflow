from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def main():
    root = PROJECT / "outputs" / "doe"
    rows = []
    failures = []
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        case_id = case_dir.name
        design_path = case_dir / f"{case_id}_design.json"
        model_path = case_dir / f"{case_id}.vsp3"
        schedule_path = case_dir / f"{case_id}_section_schedule.csv"
        missing = [
            str(path.name)
            for path in [design_path, model_path, schedule_path]
            if not path.exists()
        ]
        if missing:
            failures.append({"case_id": case_id, "missing": ";".join(missing)})
            continue
        design = json.loads(design_path.read_text(encoding="utf-8"))
        with schedule_path.open(newline="", encoding="utf-8-sig") as handle:
            schedule = list(csv.DictReader(handle))
        rows.append({
            "case_id": case_id,
            "x_h_over_c": design["x_h_over_c"],
            "A_max_over_c": design["A_max_over_c"],
            "shape_type": design["shape_type"],
            "eta_start": design["eta_start"],
            "eta_end": design["eta_end"],
            "geometric_section_count": len(schedule),
            "morphed_section_count": sum(row["morphed"] == "True" for row in schedule),
            "max_abs_TE_displacement_m": max(
                abs(float(row["TE_displacement_m"])) for row in schedule
            ),
            "model_size_bytes": model_path.stat().st_size,
            "complete": True,
        })
    manifest = root / "minimal_doe_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    failure_path = root / "minimal_doe_generation_failures.csv"
    with failure_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "missing"])
        writer.writeheader()
        writer.writerows(failures)
    expected = json.loads(
        (PROJECT / "config" / "minimal_doe_cases.json").read_text(encoding="utf-8")
    )
    expected_ids = {case["case_id"] for case in expected}
    generated_ids = {row["case_id"] for row in rows}
    absent = sorted(expected_ids - generated_ids)
    print(
        f"DOE audit: expected={len(expected_ids)}, complete={len(rows)}, "
        f"incomplete={len(failures)}, absent={len(absent)}"
    )
    if failures or absent:
        raise RuntimeError(f"DOE generation incomplete; absent={absent}")


if __name__ == "__main__":
    main()


