from __future__ import annotations

import csv
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
FACTOR = 0.3048
MARKER = "native_ft_to_si_2026_07_28"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def correct_table(path: Path, fields: list[str]) -> bool:
    rows = read_csv(path)
    if not rows or rows[0].get("kinematic_unit_audit") == MARKER:
        return False
    for row in rows:
        for field in fields:
            if row.get(field, ""):
                row[field] = repr(float(row[field]) * FACTOR)
        row["kinematic_unit_audit"] = MARKER
    write_csv(path, rows)
    return True


def main() -> None:
    outputs = PROJECT / "outputs"
    corrected: list[Path] = []
    summary_fields = ["max_le_travel_mm", "max_te_travel_mm"]
    for path in [
        outputs / "axis_sensitivity_cases/axis_sensitivity_manifest.csv",
        outputs / "fixed_cl_axis_sensitivity/fixed_cl_axis_sensitivity_summary.csv",
        *sorted((outputs / "fixed_cl_axis_sensitivity").glob("*_fixed_cl_summary.csv")),
    ]:
        if path.exists() and correct_table(path, summary_fields):
            corrected.append(path)

    schedule_fields = [
        "leading_edge_dx_m",
        "leading_edge_dz_m",
        "leading_edge_travel_m",
        "trailing_edge_dx_m",
        "trailing_edge_dz_m",
        "trailing_edge_travel_m",
    ]
    for path in sorted((outputs / "axis_sensitivity_cases").glob("*/*_twist_schedule.csv")):
        if correct_table(path, schedule_fields):
            corrected.append(path)

    print(f"Corrected {len(corrected)} legacy axis-kinematics files.")


if __name__ == "__main__":
    main()

