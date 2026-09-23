"""Propose a small exact-validation batch for the corrected Mach-0.1 CDiw study."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict


PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT.parent
AUDIT = PROJECT / "outputs" / "corrected_low_speed_far_field_audit"
OUTPUT = PROJECT / "outputs" / "corrected_low_speed_far_field_optimization"
CONTROL_COLUMNS = [f"u{index}" for index in range(1, 6)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--samples", type=int, default=250000)
    parser.add_argument("--batch-size", type=int, default=4)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def design_path(row: dict[str, str]) -> Path:
    case_id = row["case_id"]
    if row["concept"] == "trailing_edge":
        return (
            WORK / "argus_morphing" / "outputs" / "corrected_te_optimization"
            / "samples" / case_id / f"{case_id}_design.json"
        )
    return (
        WORK / "argus_twist_morphing" / "outputs" / "corrected_twist_optimization"
        / "samples" / case_id / f"{case_id}_design.json"
    )


def control_values(row: dict[str, str]) -> list[float]:
    design = json.loads(design_path(row).read_text(encoding="utf-8"))
    key = (
        "control_amplitudes_over_c"
        if row["concept"] == "trailing_edge"
        else "control_twist_deg"
    )
    return [float(value) for value in design[key]]


def scale(values: np.ndarray, lower: float, upper: float) -> np.ndarray:
    return 2.0 * (values - lower) / (upper - lower) - 1.0


def model(seed: int, restarts: int = 3) -> GaussianProcessRegressor:
    kernel = (
        ConstantKernel(1.0, (0.05, 20.0))
        * Matern(np.ones(5), (0.08, 10.0), nu=2.5)
        + WhiteKernel(1.0e-7, (1.0e-10, 1.0e-3))
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        n_restarts_optimizer=restarts,
        random_state=seed,
    )


def fit(
    x: np.ndarray,
    y: np.ndarray,
    seed: int,
) -> tuple[GaussianProcessRegressor, dict]:
    fitted = model(seed)
    fitted.fit(x, y)
    folds = KFold(n_splits=5, shuffle=True, random_state=seed)
    predicted = cross_val_predict(model(seed, restarts=0), x, y, cv=folds)
    return fitted, {
        "sample_count": len(y),
        "training_rmse": mean_squared_error(y, fitted.predict(x)) ** 0.5,
        "cross_validation_rmse": mean_squared_error(y, predicted) ** 0.5,
        "cross_validation_r2": r2_score(y, predicted),
        "kernel": str(fitted.kernel_),
    }


def candidates(
    rng: np.random.Generator,
    concept: str,
    count: int,
) -> tuple[np.ndarray, float, float]:
    if concept == "trailing_edge":
        lower, upper, adjacent = 0.0, 0.035, 0.018
    else:
        lower, upper, adjacent = -1.0, 4.0, 2.5
    accepted: list[np.ndarray] = []
    remaining = count
    while remaining:
        trial = rng.uniform(lower, upper, size=(max(remaining * 4, 20000), 5))
        if concept == "trailing_edge":
            extended = np.column_stack([np.zeros(len(trial)), trial, np.zeros(len(trial))])
        else:
            extended = np.column_stack([np.zeros(len(trial)), trial])
        valid = trial[np.max(np.abs(np.diff(extended, axis=1)), axis=1) <= adjacent]
        take = min(remaining, len(valid))
        accepted.append(valid[:take])
        remaining -= take
    return np.vstack(accepted), lower, upper


def distinct_ranked(
    rankings: list[tuple[str, np.ndarray]],
    x_scaled: np.ndarray,
    training_scaled: np.ndarray,
    count: int,
    minimum_distance: float,
) -> list[tuple[str, int]]:
    selected: list[tuple[str, int]] = []
    vectors: list[np.ndarray] = []
    for reason, ranking in rankings:
        for index in ranking:
            vector = x_scaled[index]
            if np.min(np.linalg.norm(training_scaled - vector, axis=1)) < minimum_distance:
                continue
            if any(np.linalg.norm(vector - previous) < minimum_distance for previous in vectors):
                continue
            selected.append((reason, int(index)))
            vectors.append(vector)
            break
        if len(selected) >= count:
            return selected
    if len(selected) < count:
        for index in rankings[0][1]:
            vector = x_scaled[index]
            if np.min(np.linalg.norm(training_scaled - vector, axis=1)) < minimum_distance:
                continue
            if any(np.linalg.norm(vector - previous) < minimum_distance for previous in vectors):
                continue
            selected.append(("predicted_minimum_diverse", int(index)))
            vectors.append(vector)
            if len(selected) >= count:
                break
    return selected


def main() -> None:
    args = parse_args()
    audit_rows = read_csv(AUDIT / "all_ranked_results.csv")
    baseline = next(row for row in audit_rows if row["concept"] == "rigid")
    baseline_cdiw = float(baseline["CDiw_far_field"])
    output = OUTPUT / f"proposal_batch_{args.batch:02d}"
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260818 + args.batch)
    diagnostics: list[dict] = []
    predictions: list[dict] = []

    for concept, prefix in [("trailing_edge", "cfft"), ("twist", "cffw")]:
        rows = [row for row in audit_rows if row["concept"] == concept]
        controls = np.asarray([control_values(row) for row in rows])
        trial, lower, upper = candidates(rng, concept, args.samples)
        x = scale(controls, lower, upper)
        trial_scaled = scale(trial, lower, upper)
        cdiw = np.asarray([float(row["CDiw_far_field"]) for row in rows])
        bending = np.asarray([float(row["root_bending_increase_percent"]) for row in rows])
        cdiw_model, cdiw_diag = fit(x, cdiw, 100 * args.batch)
        bending_model, bending_diag = fit(x, bending, 100 * args.batch + 1)
        diagnostics.extend(
            [
                {"concept": concept, "target": "CDiw", **cdiw_diag},
                {"concept": concept, "target": "root_bending_increase_percent", **bending_diag},
            ]
        )
        mean, std = cdiw_model.predict(trial_scaled, return_std=True)
        bend_mean, bend_std = bending_model.predict(trial_scaled, return_std=True)
        robust_feasible = bend_mean + 0.5 * bend_std <= 6.8
        feasible_indices = np.flatnonzero(robust_feasible)
        if not len(feasible_indices):
            raise RuntimeError(f"No predicted feasible candidates for {concept}")
        min_rank = feasible_indices[np.argsort(mean[feasible_indices])]
        lcb_rank = feasible_indices[np.argsort((mean - 0.75 * std)[feasible_indices])]
        boundary_rank = feasible_indices[
            np.lexsort((mean[feasible_indices], -bend_mean[feasible_indices]))
        ]
        uncertain_rank = feasible_indices[np.argsort(-std[feasible_indices])]
        chosen = distinct_ranked(
            [
                ("predicted_minimum", min_rank),
                ("lower_confidence_bound", lcb_rank),
                ("near_bending_boundary", boundary_rank),
                ("uncertainty_exploration", uncertain_rank),
            ],
            trial_scaled,
            x,
            args.batch_size,
            minimum_distance=0.12,
        )

        designs: list[dict] = []
        for number, (reason, index) in enumerate(chosen, start=1):
            values = trial[index].tolist()
            case_id = f"{prefix}_b{args.batch:02d}_c{number:02d}"
            common = {
                "case_id": case_id,
                "iteration": args.batch,
                "eta_start": 0.6,
                "eta_end": 1.0,
                "shape_type": "control_points",
                "alpha_deg": 2.0,
                "mach": 0.1,
                "proposal_reason": reason,
                "notes": "Corrected-airfoil candidate proposed from native CDiw surrogate.",
            }
            if concept == "trailing_edge":
                extended = [0.0, *values, 0.0]
                design = {
                    **common,
                    "x_h_over_c": 0.62,
                    "A_max_over_c": max(values),
                    "control_etas": [0.6, 0.7, 0.8, 0.9, 1.0],
                    "control_amplitudes_over_c": values,
                    "max_adjacent_delta": max(
                        abs(right - left) for left, right in zip(extended, extended[1:])
                    ),
                    "max_spanwise_slope": max(
                        abs(right - left) / 0.1 for left, right in zip(values, values[1:])
                    ),
                }
            else:
                extended = [0.0, *values]
                design = {
                    **common,
                    "control_etas": [0.68, 0.76, 0.84, 0.92, 1.0],
                    "control_twist_deg": values,
                    "rotation_axis_x_over_c": 0.25,
                    "max_adjacent_twist_delta_deg": max(
                        abs(right - left) for left, right in zip(extended, extended[1:])
                    ),
                }
            designs.append(design)
            predictions.append(
                {
                    "case_id": case_id,
                    "concept": concept,
                    "proposal_reason": reason,
                    **{name: value for name, value in zip(CONTROL_COLUMNS, values)},
                    "predicted_CDiw": mean[index],
                    "predicted_CDiw_reduction_percent": 100.0 * (baseline_cdiw - mean[index]) / baseline_cdiw,
                    "predicted_CDiw_std": std[index],
                    "predicted_root_bending_increase_percent": bend_mean[index],
                    "predicted_root_bending_std_percent": bend_std[index],
                }
            )
        target = (
            WORK / "argus_morphing" / "config" / f"corrected_cdiw_batch_{args.batch:02d}_cases.json"
            if concept == "trailing_edge"
            else WORK / "argus_twist_morphing" / "config" / f"corrected_cdiw_batch_{args.batch:02d}_cases.json"
        )
        target.write_text(json.dumps(designs, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(designs)} {concept} candidates to {target}")

    write_csv(output / "surrogate_diagnostics.csv", diagnostics)
    write_csv(output / "candidate_predictions.csv", predictions)


if __name__ == "__main__":
    main()

