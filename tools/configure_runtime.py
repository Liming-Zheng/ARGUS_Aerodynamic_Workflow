"""Create machine-local JSON configs from portable ``*.template.json`` files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def replace_string(value: str, repo: Path, args: argparse.Namespace) -> str:
    normalized = value.replace("\\", "/")
    placeholder_replacements = {
        "${ARGUS_REPO_ROOT}": str(repo),
        "${OPENVSP_ROOT}": args.openvsp_root,
        "${OPENVSP_PYTHON}": args.openvsp_python,
        "${GENERAL_PYTHON}": args.general_python,
    }
    for old, new in placeholder_replacements.items():
        normalized = normalized.replace(old, str(Path(new).resolve()))
    return normalized


def rewrite(value, repo: Path, args: argparse.Namespace):
    if isinstance(value, dict):
        return {key: rewrite(item, repo, args) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite(item, repo, args) for item in value]
    if isinstance(value, str):
        return replace_string(value, repo, args)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openvsp-root", required=True)
    parser.add_argument("--openvsp-python", required=True)
    parser.add_argument("--general-python", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    templates = sorted(repo.glob("studies/**/config/*.template.json"))
    if not templates:
        raise SystemExit("No configuration templates found.")

    for template in templates:
        target = template.with_name(template.name.replace(".template.json", ".json"))
        data = rewrite(json.loads(template.read_text(encoding="utf-8")), repo, args)
        print(f"{template.relative_to(repo)} -> {target.relative_to(repo)}")
        if not args.dry_run:
            target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    if not args.dry_run:
        runtime = {
            "openvsp_root": str(Path(args.openvsp_root).resolve()),
            "openvsp_python": str(Path(args.openvsp_python).resolve()),
            "general_python": str(Path(args.general_python).resolve()),
        }
        (repo / ".argus_runtime.json").write_text(
            json.dumps(runtime, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

