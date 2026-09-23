from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_conventional_control.atmosphere import flight_state
from argus_conventional_control.scaling import build_scale_definition


def write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    config = json.loads(
        (PROJECT / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    scale = build_scale_definition(config)
    area = float(scale["aircraft_reference_area_m2"])
    states = [
        flight_state(
            name=row["name"],
            altitude_m=float(row["altitude_m"]),
            mach=float(row["mach"]),
            mass_equivalent_kg=float(row["mass_equivalent_kg"]),
            reference_area_m2=area,
        )
        for row in config["flight_states"]
    ]
    output = PROJECT / "outputs" / "study_definition"
    output.mkdir(parents=True, exist_ok=True)
    (output / "scale_definition.json").write_text(
        json.dumps(scale, indent=2) + "\n", encoding="utf-8"
    )
    (output / "flight_states.json").write_text(
        json.dumps(states, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(output / "flight_states.csv", states)
    print(f"Wrote scale and {len(states)} flight states to {output}")
    for state in states:
        print(
            f"{state['name']}: CL={state['target_CL']:.6f}, "
            f"q={state['dynamic_pressure_Pa']:.1f} Pa"
        )


if __name__ == "__main__":
    main()

