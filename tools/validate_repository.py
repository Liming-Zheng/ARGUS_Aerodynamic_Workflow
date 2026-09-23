"""Static checks for a clean, internally consistent handover repository."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    failures: list[str] = []

    required = [
        repo / "README.md",
        repo / "inputs" / "geometry" / "baseline_corrected.vsp3",
        repo / "results" / "cruise" / "final_concept_summary.csv",
        repo / "results" / "low_speed" / "final_concept_summary.csv",
    ]
    for path in required:
        if not path.exists():
            failures.append(f"missing required file: {path.relative_to(repo)}")

    for path in repo.glob("studies/**/config/*.template.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # report exact malformed template
            failures.append(f"invalid JSON {path.relative_to(repo)}: {exc}")

    absolute_pattern = re.compile(r"[A-Za-z]:[/\\](?:ARGUS|Users)[/\\]", re.I)
    for pattern in ("*.py", "*.md", "*.json", "*.csv"):
        for path in repo.rglob(pattern):
            if ".git" in path.parts or path.name == "PROJECT_HISTORY.md":
                continue
            if path.name == ".argus_runtime.json":
                continue
            if path.parent.name == "config" and not path.name.endswith(".template.json"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if absolute_pattern.search(text):
                failures.append(f"machine-specific path remains: {path.relative_to(repo)}")

    cruise = repo / "results" / "cruise" / "final_concept_summary.csv"
    if cruise.exists():
        with cruise.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows or any(row.get("ranking_metric") != "CDiw" for row in rows):
            failures.append("cruise summary must explicitly use CDiw")

    if failures:
        print("Repository validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

