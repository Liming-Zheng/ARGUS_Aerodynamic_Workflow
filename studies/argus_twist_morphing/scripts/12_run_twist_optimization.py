from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(__file__).resolve().parents[1]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT / "config" / "optimization_twist_cdi_config.json",
    )
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-evaluate", action="store_true")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sample_rows(project: Path, config: dict) -> list[dict]:
    rows = read_csv(project / "outputs" / "optimization" / "optimization_samples.csv")
    prefixes = (config["seed_prefix"], config["case_prefix"])
    return [row for row in rows if row["case_id"].startswith(prefixes)]


def best_row(rows: list[dict]) -> dict:
    if not rows:
        raise RuntimeError("No twist optimization samples are available")
    return min(rows, key=lambda row: float(row["CDi"]))


def max_adjacent(values: list[float]) -> float:
    return max(abs(right - left) for left, right in zip(values, values[1:]))


def valid(values: list[float], config: dict) -> bool:
    lower, upper = config["design_variables"]["twist_bounds_deg"]
    if any(value < lower or value > upper for value in values):
        return False
    return max_adjacent(values) <= float(
        config["design_variables"]["max_adjacent_twist_delta_deg"]
    )


def deterministic_candidates(config: dict, iteration: int) -> list[list[float]]:
    if iteration == 1:
        candidates = [
            [0.0, 2.5, 2.5, 2.5, 0.0],
            [0.0, 2.0, 3.5, 2.0, 0.0],
            [0.0, 2.5, 3.5, 2.5, 0.0],
            [0.0, 1.5, 3.0, 3.0, 0.5],
        ]
    else:
        candidates = [
            [0.0, 2.5, 4.0, 2.5, 0.0],
            [0.0, 2.0, 4.0, 3.0, 0.5],
            [0.0, 2.5, 3.5, 3.0, 0.5],
            [0.0, 3.0, 3.5, 2.0, 0.0],
        ]
    return [values for values in candidates if valid(values, config)]


def candidate_designs(values_batch: list[list[float]], config: dict, iteration: int) -> list[dict]:
    variables = config["design_variables"]
    designs = []
    for index, values in enumerate(values_batch, start=1):
        designs.append({
            "case_id": f"{config['case_prefix']}_i{iteration:03d}_c{index:02d}",
            "iteration": iteration,
            "eta_start": variables["eta_start"],
            "eta_end": variables["eta_end"],
            "rotation_axis_x_over_c": variables["rotation_axis_x_over_c"],
            "control_etas": variables["control_etas"],
            "control_twist_deg": values,
            "max_adjacent_twist_delta_deg": max_adjacent(values),
            "max_abs_twist_deg": max(abs(value) for value in values),
            "notes": f"Twist optimization iteration {iteration}",
        })
    return designs


def run_command(command: list[object], project: Path, log_path: Path):
    completed = subprocess.run(
        [str(item) for item in command],
        cwd=project,
        capture_output=True,
        text=True,
    )
    log_path.write_text(completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(f"Command failed; see {log_path}")


def update_plots(run_root: Path, rows: list[dict], history: list[dict], config: dict):
    plt.rcParams["svg.fonttype"] = "none"
    if history:
        fig, ax = plt.subplots(figsize=(8.5, 5.0))
        ax.plot(
            [int(row["iteration"]) for row in history],
            [float(row["best_CDi"]) for row in history],
            color="#174A6B",
            marker="o",
            lw=2.2,
        )
        ax.set_xlabel("Iteration")
        ax.set_ylabel(r"Best exact $C_{D_i}$")
        ax.set_title("Twist optimization convergence")
        ax.grid(alpha=0.25)
        fig.savefig(run_root / "iteration_convergence.svg", bbox_inches="tight")
        fig.savefig(run_root / "iteration_convergence.png", dpi=220, bbox_inches="tight")
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.scatter(
        [float(row["root_bending_change_percent"]) for row in rows],
        [float(row["CDi"]) for row in rows],
        color="#237A72",
    )
    for row in rows:
        if row["case_id"] == best_row(rows)["case_id"]:
            ax.scatter(
                [float(row["root_bending_change_percent"])],
                [float(row["CDi"])],
                color="#C56A32",
                marker="*",
                s=180,
                label="Best exact sample",
            )
    ax.set_xlabel("Root bending change [%]")
    ax.set_ylabel(r"$C_{D_i}$")
    ax.set_title("Twist optimization exact sample space")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.savefig(run_root / "current_exact_design_space.svg", bbox_inches="tight")
    fig.savefig(run_root / "current_exact_design_space.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    best = best_row(rows)
    etas = config["design_variables"]["control_etas"]
    values = [float(best[f"T{i}_deg"]) for i in range(1, len(etas) + 1)]
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ax.plot(etas, values, color="#4E8B57", marker="o", lw=2.2)
    ax.axhline(0.0, color="#5B6670", lw=1)
    ax.set_xlabel(r"$\eta=y/(b/2)$")
    ax.set_ylabel("Incremental twist [deg]")
    ax.set_title(f"Current best twist schedule: {best['case_id']}")
    ax.grid(alpha=0.25)
    fig.savefig(run_root / "current_best_twist_schedule.svg", bbox_inches="tight")
    fig.savefig(run_root / "current_best_twist_schedule.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def main():
    args = parse_args()
    project = args.project.resolve()
    config_path = args.config if args.config.is_absolute() else project / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.iterations is not None:
        config["iterations"]["max_iterations"] = args.iterations
    rows = sample_rows(project, config)
    print(f"Configuration valid. Exact samples={len(rows)}")
    if rows:
        print(f"Best CDi={float(best_row(rows)['CDi']):.9g} ({best_row(rows)['case_id']})")
    if args.dry_run:
        return

    run_root = project / "outputs" / "optimization" / config["run_name"]
    run_root.mkdir(parents=True, exist_ok=True)
    history_path = run_root / "iteration_history.csv"
    history = read_csv(history_path)
    if not history and rows:
        history = [{
            "iteration": 0,
            "best_case": best_row(rows)["case_id"],
            "best_CDi": best_row(rows)["CDi"],
            "new_samples": 0,
        }]
        write_csv(history_path, history)

    openvsp_python = Path(config["runtime"]["openvsp_python"])
    max_iter = int(config["iterations"]["max_iterations"])
    completed = max((int(row["iteration"]) for row in history), default=0)
    for iteration in range(completed + 1, max_iter + 1):
        designs = candidate_designs(deterministic_candidates(config, iteration), config, iteration)
        cases_path = run_root / f"iteration_{iteration:03d}_cases.json"
        cases_path.write_text(json.dumps(designs, indent=2) + "\n", encoding="utf-8")
        print(f"Iteration {iteration}: proposed {len(designs)} candidates")
        if args.no_evaluate:
            return
        run_command(
            [
                openvsp_python,
                project / "scripts" / "10_generate_twist_optimization_cases.py",
                "--cases",
                cases_path,
                "--output-root",
                project / "outputs" / "optimization" / "samples",
            ],
            project,
            run_root / f"iteration_{iteration:03d}_generate.log",
        )
        run_command(
            [
                openvsp_python,
                project / "scripts" / "11_run_twist_optimization_samples.py",
                "--workers",
                config["runtime"]["workers"],
                "--cl-tolerance",
                config["runtime"]["cl_tolerance"],
            ],
            project,
            run_root / f"iteration_{iteration:03d}_evaluate.log",
        )
        rows = sample_rows(project, config)
        best = best_row(rows)
        history.append({
            "iteration": iteration,
            "best_case": best["case_id"],
            "best_CDi": best["CDi"],
            "new_samples": len(designs),
        })
        write_csv(history_path, history)
        update_plots(run_root, rows, history, config)
        (run_root / "current_best_design.json").write_text(
            json.dumps(best, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Iteration {iteration} complete: best CDi={float(best['CDi']):.9g}")

    rows = sample_rows(project, config)
    update_plots(run_root, rows, history, config)
    (run_root / "current_best_design.json").write_text(
        json.dumps(best_row(rows), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Optimization run complete. Results: {run_root}")


if __name__ == "__main__":
    main()

