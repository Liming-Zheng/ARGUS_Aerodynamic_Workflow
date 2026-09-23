"""Check the local Python/OpenVSP setup after runtime configuration."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    runtime_file = repo / ".argus_runtime.json"
    if not runtime_file.exists():
        print("FAIL: run tools/configure_runtime.py first")
        return 1

    runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
    failures = 0
    for key, value in runtime.items():
        path = Path(value)
        ok = path.exists()
        print(f"{'OK' if ok else 'FAIL'}: {key} = {path}")
        failures += int(not ok)

    for package in ("numpy", "pandas", "scipy", "sklearn", "matplotlib"):
        ok = importlib.util.find_spec(package) is not None
        print(f"{'OK' if ok else 'FAIL'}: Python package {package}")
        failures += int(not ok)

    baseline = repo / "inputs" / "geometry" / "baseline_corrected.vsp3"
    ok = baseline.exists()
    print(f"{'OK' if ok else 'FAIL'}: corrected baseline geometry")
    failures += int(not ok)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())


