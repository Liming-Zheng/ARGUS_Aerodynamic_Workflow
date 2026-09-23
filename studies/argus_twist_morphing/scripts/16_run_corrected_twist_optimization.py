"""Run the configurable, iterative ARGUS optimization workflow.

Use the general Python environment for this script. It trains the surrogate,
proposes a batch, asks the OpenVSP Python environment to generate/evaluate the
batch, then records exact improvement before starting the next iteration.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from argus_twist_morphing.optimization_framework import (  # noqa: E402
    adjacent_deltas,
    exact_objective,
    fit_models,
    filtered_exact_samples,
    include_boundary_zeros,
    is_feasible,
    objective_definition,
    propose_batch,
    validate_user_config,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Configurable iterative optimizer for the ARGUS morphing wing."
    )
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT / "config" / "optimization_user_config.json",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        help="Override max_iterations in the JSON for this run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and data without proposing or evaluating cases.",
    )
    parser.add_argument(
        "--no-evaluate",
        action="store_true",
        help="Write the next proposed batch JSON, but do not call OpenVSP.",
    )
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="Start iteration numbering again; exact sample files are not deleted.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    fields = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def best_feasible(rows, config):
    definition = objective_definition(config)
    feasible = [row for row in rows if is_feasible(row, config)]
    if not feasible:
        raise RuntimeError("No exact sample satisfies the active constraints")
    return min(feasible, key=lambda row: exact_objective(row, definition))


def displayed_metric(row, config):
    return float(row[config["objective"]["metric"]])


def candidate_designs(values_batch, config, iteration):
    variables = config["design_variables"]
    prefix = config.get("case_prefix", "usr")
    designs = []
    for batch_index, values in enumerate(values_batch, start=1):
        case_id = f"{prefix}_i{iteration:03d}_c{batch_index:02d}"
        designs.append({
            "case_id": case_id,
            "iteration": iteration,
            "eta_start": variables["eta_start"],
            "eta_end": variables["eta_end"],
            "rotation_axis_x_over_c": variables["rotation_axis_x_over_c"],
            "shape_type": "distributed_section_twist",
            "control_etas": variables["control_etas"],
            "control_twist_deg": values,
            "max_adjacent_twist_delta_deg": float(
                max(
                    adjacent_deltas(
                        values,
                        include_boundary_zeros(config),
                    )
                )
            ),
            "max_spanwise_slope": max(
                abs(right - left) / (right_eta - left_eta)
                for left, right, left_eta, right_eta in zip(
                    values,
                    values[1:],
                    variables["control_etas"],
                    variables["control_etas"][1:],
                )
            ),
            "alpha_deg": 2.0,
            "mach": 0.10,
            "notes": f"Corrected distributed-twist optimization iteration {iteration}",
        })
    return designs


def run_command(command, project, log_path):
    """Run a child stage and preserve its output in a readable log file."""
    completed = subprocess.run(
        [str(item) for item in command],
        cwd=project,
        capture_output=True,
        text=True,
    )
    log_path.write_text(
        completed.stdout + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(f"Command failed; see {log_path}")


def update_plots(output: Path, history: list[dict], samples: list[dict], config):
    plt.rcParams["svg.fonttype"] = "none"
    iterations = [int(row["iteration"]) for row in history]
    best_values = [float(row["best_metric_after"]) for row in history]
    improvements = [float(row["improvement_percent"]) for row in history]

    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.plot(iterations, best_values, color="#174A6B", marker="o", lw=2.2)
    ax.set_xlabel("Completed outer iteration")
    ax.set_ylabel(f"Best exact {config['objective']['metric']}")
    ax.set_title("ARGUS exact optimization convergence")
    ax.set_xticks(iterations)
    ax.set_xlim(min(iterations) - 0.25, max(iterations) + 0.25)
    ax.grid(alpha=0.25)
    fig.savefig(output / "iteration_convergence.svg", bbox_inches="tight")
    fig.savefig(output / "iteration_convergence.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5.2))
    bars = ax.bar(iterations, improvements, color="#237A72")
    ax.bar_label(bars, fmt="%.3f%%", padding=3, fontsize=9)
    ax.axhline(0.0, color="#5B6670", lw=1)
    ax.set_xlabel("Completed outer iteration")
    ax.set_ylabel("Improvement during iteration [%]")
    ax.set_title("Exact improvement delivered by each VSPAERO batch")
    ax.set_xticks(iterations)
    ax.set_xlim(min(iterations) - 0.5, max(iterations) + 0.5)
    ax.grid(axis="y", alpha=0.25)
    fig.savefig(output / "iteration_improvement.svg", bbox_inches="tight")
    fig.savefig(output / "iteration_improvement.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    feasible = [row for row in samples if is_feasible(row, config)]
    infeasible = [row for row in samples if not is_feasible(row, config)]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.scatter(
        [float(row["root_bending_increase_percent"]) for row in feasible],
        [float(row[config["objective"]["metric"]]) for row in feasible],
        color="#174A6B",
        label="Feasible exact samples",
    )
    ax.scatter(
        [float(row["root_bending_increase_percent"]) for row in infeasible],
        [float(row[config["objective"]["metric"]]) for row in infeasible],
        color="#B4473F",
        marker="x",
        label="Infeasible exact samples",
    )
    if config["constraints"]["root_bending"]["enabled"]:
        ax.axvline(
            config["constraints"]["root_bending"]["maximum_percent"],
            color="#C56A32",
            ls="--",
            label="Root-bending limit",
        )
    ax.set_xlabel("Root bending increase [%]")
    ax.set_ylabel(config["objective"]["metric"])
    ax.set_title("Current exact design space")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.savefig(output / "current_exact_design_space.svg", bbox_inches="tight")
    fig.savefig(output / "current_exact_design_space.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    best = best_feasible(samples, config)
    design_path = (
        output.parent
        / "samples"
        / best["case_id"]
        / f"{best['case_id']}_design.json"
    )
    if design_path.exists():
        design = json.loads(design_path.read_text(encoding="utf-8"))
        fig, ax = plt.subplots(figsize=(8.5, 5.0))
        ax.plot(
            design["control_etas"],
            design["control_twist_deg"],
            color="#4E8B57",
            marker="o",
            lw=2.2,
        )
        ax.set_xlabel("eta = y/(b/2)")
        ax.set_ylabel("Incremental section twist [deg]")
        ax.set_title(f"Current best exact design: {best['case_id']}")
        ax.grid(alpha=0.25)
        fig.savefig(output / "current_best_spanwise_schedule.svg", bbox_inches="tight")
        fig.savefig(
            output / "current_best_spanwise_schedule.png",
            dpi=220,
            bbox_inches="tight",
        )
        plt.close(fig)


def main():
    args = parse_args()
    project = args.project.resolve()
    config_path = args.config if args.config.is_absolute() else project / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_user_config(config)
    if args.iterations is not None:
        config["iterations"]["max_iterations"] = args.iterations

    paths = config.get("paths", {})
    optimization_root = Path(
        paths.get("optimization_root", project / "outputs" / "optimization")
    )
    if not optimization_root.is_absolute():
        optimization_root = project / optimization_root
    baseline_model = Path(
        paths.get(
            "baseline_model",
            project
            / "outputs"
            / "refined_baseline"
            / "baseline_wing_only_refined.vsp3",
        )
    )
    if not baseline_model.is_absolute():
        baseline_model = project / baseline_model
    solver_config = Path(
        paths.get(
            "solver_config",
            project / "config" / "optimization_config.json",
        )
    )
    if not solver_config.is_absolute():
        solver_config = project / solver_config
    samples_path = optimization_root / "optimization_samples.csv"
    samples = filtered_exact_samples(read_csv(samples_path), config)
    current_best = best_feasible(samples, config)
    print(
        f"Configuration valid. Exact samples={len(samples)}, "
        f"best {config['objective']['metric']}={displayed_metric(current_best, config):.9g}"
    )
    if args.dry_run:
        print("Dry run complete; no files or OpenVSP models were changed.")
        return

    run_root = optimization_root / config["run_name"]
    run_root.mkdir(parents=True, exist_ok=True)
    history_path = run_root / "iteration_history.csv"
    if args.reset_history and history_path.exists():
        history_path.unlink()
    history = read_csv(history_path) if history_path.exists() else []
    if not history:
        initial_best = best_feasible(samples, config)
        initial_score = exact_objective(
            initial_best,
            objective_definition(config),
        )
        history = [{
            "iteration": 0,
            "new_exact_samples": 0,
            "new_feasible_samples": 0,
            "total_exact_samples": len(samples),
            "best_case_before": initial_best["case_id"],
            "best_case_after": initial_best["case_id"],
            "best_metric_before": displayed_metric(initial_best, config),
            "best_metric_after": displayed_metric(initial_best, config),
            "objective_score_before": initial_score,
            "objective_score_after": initial_score,
            "absolute_improvement": 0.0,
            "improvement_percent": 0.0,
            "elapsed_seconds": 0.0,
        }]
        write_csv(history_path, history)
        update_plots(run_root, history, samples, config)
    completed_iterations = max(
        (int(row["iteration"]) for row in history),
        default=0,
    )
    maximum_iterations = int(config["iterations"]["max_iterations"])
    low_improvement_count = 0
    for row in reversed(history):
        if float(row["absolute_improvement"]) < float(
            config["iterations"]["minimum_absolute_improvement"]
        ):
            low_improvement_count += 1
        else:
            break

    for iteration in range(completed_iterations + 1, maximum_iterations + 1):
        start_time = time.perf_counter()
        samples_before = filtered_exact_samples(read_csv(samples_path), config)
        best_before = best_feasible(samples_before, config)
        internal_before = exact_objective(best_before, objective_definition(config))
        models = fit_models(samples_before, config)
        values_batch = propose_batch(models, config, iteration)
        designs = candidate_designs(values_batch, config, iteration)
        cases_path = run_root / f"iteration_{iteration:03d}_cases.json"
        cases_path.write_text(json.dumps(designs, indent=2) + "\n", encoding="utf-8")
        print(f"Iteration {iteration}: proposed {len(designs)} candidates")
        if args.no_evaluate:
            print(f"Proposal written to {cases_path}; OpenVSP evaluation skipped.")
            return

        openvsp_python = Path(config["runtime"]["openvsp_python"])
        generate_log = run_root / f"iteration_{iteration:03d}_generate.log"
        evaluate_log = run_root / f"iteration_{iteration:03d}_evaluate.log"
        run_command(
            [
                openvsp_python,
                project / "scripts" / "13_generate_corrected_twist_cases.py",
                "--cases",
                cases_path,
                "--output-root",
                optimization_root / "samples",
                "--baseline-model",
                baseline_model,
            ],
            project,
            generate_log,
        )
        run_command(
            [
                openvsp_python,
                project / "scripts" / "14_run_corrected_twist_samples.py",
                "--workers",
                config["runtime"]["workers"],
                "--trim-mode",
                config["runtime"].get("trim_mode", "fast"),
                "--alpha-low",
                config["runtime"].get("fast_trim_alpha_low", 1.0),
                "--alpha-high",
                config["runtime"].get("fast_trim_alpha_high", 2.5),
                "--alpha-points",
                config["runtime"].get("fast_trim_alpha_points", 2),
                "--cl-tolerance",
                config["runtime"].get("search_cl_tolerance", 2.0e-4),
                "--optimization-root",
                optimization_root,
                "--optimization-config",
                solver_config,
                "--baseline-config",
                project / "config" / "corrected_baseline_config.json",
            ],
            project,
            evaluate_log,
        )

        samples_after = filtered_exact_samples(read_csv(samples_path), config)
        best_after = best_feasible(samples_after, config)
        internal_after = exact_objective(best_after, objective_definition(config))
        improvement = internal_before - internal_after
        improvement_percent = (
            100.0 * improvement / abs(internal_before)
            if abs(internal_before) > 1.0e-15
            else 0.0
        )
        iteration_rows = [
            row for row in samples_after
            if row["case_id"].startswith(f"{config.get('case_prefix', 'usr')}_i{iteration:03d}_")
        ]
        feasible_new = [row for row in iteration_rows if is_feasible(row, config)]
        evaluation_seconds = [
            float(row["evaluation_seconds"])
            for row in iteration_rows
            if row.get("evaluation_seconds")
        ]
        execution_counts = [
            int(float(row["vspaero_execution_count"]))
            for row in iteration_rows
            if row.get("vspaero_execution_count")
        ]
        history.append({
            "iteration": iteration,
            "new_exact_samples": len(iteration_rows),
            "new_feasible_samples": len(feasible_new),
            "total_exact_samples": len(samples_after),
            "best_case_before": best_before["case_id"],
            "best_case_after": best_after["case_id"],
            "best_metric_before": displayed_metric(best_before, config),
            "best_metric_after": displayed_metric(best_after, config),
            "objective_score_before": internal_before,
            "objective_score_after": internal_after,
            "absolute_improvement": improvement,
            "improvement_percent": improvement_percent,
            "elapsed_seconds": time.perf_counter() - start_time,
            "mean_candidate_evaluation_seconds": (
                sum(evaluation_seconds) / len(evaluation_seconds)
                if evaluation_seconds
                else ""
            ),
            "total_vspaero_executions": sum(execution_counts),
        })
        write_csv(history_path, history)
        update_plots(run_root, history, samples_after, config)
        print(
            f"Iteration {iteration} complete: best "
            f"{config['objective']['metric']}={displayed_metric(best_after, config):.9g}, "
            f"improvement={improvement:+.3e} ({improvement_percent:+.3f}%)"
        )

        if improvement < float(config["iterations"]["minimum_absolute_improvement"]):
            low_improvement_count += 1
        else:
            low_improvement_count = 0
        if low_improvement_count >= int(config["iterations"]["early_stop_patience"]):
            print(
                "Early stopping: improvement stayed below the configured threshold "
                f"for {low_improvement_count} consecutive iterations."
            )
            break

    final_samples = filtered_exact_samples(read_csv(samples_path), config)
    update_plots(run_root, history, final_samples, config)
    final_best = best_feasible(final_samples, config)
    (run_root / "current_best_design.json").write_text(
        json.dumps(final_best, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Optimization run complete. Results: {run_root}")


if __name__ == "__main__":
    main()

