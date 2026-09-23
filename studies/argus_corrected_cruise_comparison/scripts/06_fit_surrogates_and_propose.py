"""Fit concept/state surrogates and propose an exact-validation batch."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import (
    ConstantKernel,
    Matern,
    WhiteKernel,
)
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict


CONTROL_COLUMNS = [f"u{index}" for index in range(1, 6)]


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--samples", type=int, default=200000)
    parser.add_argument(
        "--concept",
        choices=["all", "trailing_edge", "twist"],
        default="all",
        help="Limit proposal generation to one morphing concept.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def collect_training_rows(project: Path, batch: int) -> list[dict]:
    """Combine the seed DOE with exact results from earlier optimization batches."""
    rows = read_rows(
        project / "outputs" / "seed_evaluations" / "all_seed_results.csv"
    )
    evaluation_root = project / "outputs" / "optimization_evaluations"
    for path in sorted(evaluation_root.glob("batch_*_results.csv")):
        try:
            result_batch = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        if result_batch < batch:
            rows.extend(read_rows(path))
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for name in row:
            if name not in fields:
                fields.append(name)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def concept_limits(config: dict, concept: str) -> tuple[float, float, float]:
    if concept == "trailing_edge":
        settings = config["morphing"]["trailing_edge"]
        lower, upper = settings["amplitude_bounds_over_c"]
        adjacent = settings["max_adjacent_control_delta_over_c"]
    else:
        settings = config["morphing"]["twist"]
        lower, upper = settings["twist_bounds_deg"]
        adjacent = settings["max_adjacent_control_delta_deg"]
    return float(lower), float(upper), float(adjacent)


def scale_inputs(values: np.ndarray, lower: float, upper: float) -> np.ndarray:
    return 2.0 * (values - lower) / (upper - lower) - 1.0


def make_model(seed: int, restarts: int = 4) -> GaussianProcessRegressor:
    kernel = (
        ConstantKernel(1.0, (0.05, 20.0))
        * Matern(
            length_scale=np.ones(5),
            length_scale_bounds=(0.08, 10.0),
            nu=2.5,
        )
        + WhiteKernel(1.0e-7, (1.0e-10, 1.0e-3))
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        n_restarts_optimizer=restarts,
        random_state=seed,
    )


def add_baseline_anchor(
    rows: list[dict],
    baseline: dict,
    concept: str,
    state: str,
) -> list[dict]:
    selected = [
        row
        for row in rows
        if row["concept"] == concept and row["flight_state"] == state
    ]
    selected.append(
        {
            "case_id": "rigid_baseline_anchor",
            "concept": concept,
            "flight_state": state,
            **{name: 0.0 for name in CONTROL_COLUMNS},
            "CDi": baseline["CDi"],
            "half_wing_root_bending_moment_Nm": baseline[
                "half_wing_root_bending_moment_Nm"
            ],
        }
    )
    return selected


def fit_models(
    rows: list[dict],
    lower: float,
    upper: float,
    seed: int,
) -> tuple[dict[str, GaussianProcessRegressor], list[dict]]:
    x = np.array(
        [[float(row[name]) for name in CONTROL_COLUMNS] for row in rows]
    )
    x_scaled = scale_inputs(x, lower, upper)
    targets = {
        "CDi": np.array([float(row["CDi"]) for row in rows]),
        "root_bending_Nm": np.array(
            [
                float(row["half_wing_root_bending_moment_Nm"])
                for row in rows
            ]
        ),
    }
    models: dict[str, GaussianProcessRegressor] = {}
    diagnostics: list[dict] = []
    folds = KFold(n_splits=5, shuffle=True, random_state=seed)
    for index, (name, values) in enumerate(targets.items()):
        model = make_model(seed + index)
        model.fit(x_scaled, values)
        cv_model = make_model(seed + index, restarts=0)
        predicted = cross_val_predict(cv_model, x_scaled, values, cv=folds)
        models[name] = model
        diagnostics.append(
            {
                "target": name,
                "sample_count": len(rows),
                "training_rmse": mean_squared_error(
                    values, model.predict(x_scaled)
                )
                ** 0.5,
                "cross_validation_rmse": mean_squared_error(
                    values, predicted
                )
                ** 0.5,
                "cross_validation_r2": r2_score(values, predicted),
                "fitted_kernel": str(model.kernel_),
            }
        )
    return models, diagnostics


def random_smooth_designs(
    rng: np.random.Generator,
    count: int,
    lower: float,
    upper: float,
    adjacent_limit: float,
) -> np.ndarray:
    accepted: list[np.ndarray] = []
    remaining = count
    while remaining:
        batch = rng.uniform(lower, upper, size=(max(remaining * 3, 10000), 5))
        with_boundary = np.column_stack([np.zeros(len(batch)), batch])
        mask = np.max(np.abs(np.diff(with_boundary, axis=1)), axis=1) <= (
            adjacent_limit + 1.0e-12
        )
        valid = batch[mask]
        take = min(remaining, len(valid))
        accepted.append(valid[:take])
        remaining -= take
    return np.vstack(accepted)


def first_distinct(
    rankings: list[np.ndarray],
    candidates_scaled: np.ndarray,
    minimum_distance: float = 0.18,
) -> list[tuple[str, int]]:
    chosen: list[tuple[str, int]] = []
    chosen_vectors: list[np.ndarray] = []
    for reason, ranking in rankings:
        for index in ranking:
            vector = candidates_scaled[index]
            if all(
                np.linalg.norm(vector - existing) >= minimum_distance
                for existing in chosen_vectors
            ):
                chosen.append((reason, int(index)))
                chosen_vectors.append(vector)
                break
    return chosen


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    sys.path.insert(0, str(project / "src"))
    from argus_cruise_comparison.parameterization import schedule_from_iterables

    config = json.loads(
        (project / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    training_rows = collect_training_rows(project, args.batch)
    baseline_rows = {
        row["flight_state"]: row
        for row in read_rows(
            project
            / "outputs"
            / "rigid_baseline"
            / "rigid_baseline_summary.csv"
        )
    }
    root_limit = float(
        json.loads(
            (
                project
                / "outputs"
                / "rigid_baseline"
                / "constraint_definition.json"
            ).read_text(encoding="utf-8")
        )["root_bending_limit_Nm"]
    )
    output = project / "outputs" / f"surrogate_batch_{args.batch:02d}"
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260724 + args.batch)
    all_designs: list[dict] = []
    all_predictions: list[dict] = []
    all_diagnostics: list[dict] = []
    morph = config["morphing"]

    concepts = (
        ["trailing_edge", "twist"]
        if args.concept == "all"
        else [args.concept]
    )
    concept_seed_index = {"trailing_edge": 0, "twist": 1}
    for concept in concepts:
        concept_index = concept_seed_index[concept]
        lower, upper, adjacent_limit = concept_limits(config, concept)
        candidates = random_smooth_designs(
            rng, args.samples, lower, upper, adjacent_limit
        )
        candidates_scaled = scale_inputs(candidates, lower, upper)
        state_predictions: dict[str, dict[str, np.ndarray]] = {}

        for state_index, state in enumerate(["early_cruise", "late_cruise"]):
            rows = add_baseline_anchor(
                training_rows, baseline_rows[state], concept, state
            )
            models, diagnostics = fit_models(
                rows,
                lower,
                upper,
                seed=100 * concept_index + 10 * state_index + args.batch,
            )
            for item in diagnostics:
                all_diagnostics.append(
                    {"concept": concept, "flight_state": state, **item}
                )
            cdi_mean, cdi_std = models["CDi"].predict(
                candidates_scaled, return_std=True
            )
            root_mean, root_std = models["root_bending_Nm"].predict(
                candidates_scaled, return_std=True
            )
            state_predictions[state] = {
                "cdi_mean": cdi_mean,
                "cdi_std": cdi_std,
                "root_mean": root_mean,
                "root_std": root_std,
            }

        early = state_predictions["early_cruise"]
        late = state_predictions["late_cruise"]
        early_feasible = early["root_mean"] + 0.5 * early["root_std"] <= root_limit
        late_feasible = late["root_mean"] + 0.5 * late["root_std"] <= root_limit
        if not np.any(early_feasible) or not np.any(late_feasible):
            raise RuntimeError(f"No predicted feasible candidates for {concept}")

        early_rank = np.where(
            early_feasible,
            early["cdi_mean"],
            np.inf,
        ).argsort()
        boundary_score = np.where(
            early_feasible,
            early["cdi_mean"]
            + 0.2
            * np.abs(early["root_mean"] / root_limit - 0.995),
            np.inf,
        )
        boundary_rank = boundary_score.argsort()
        late_rank = np.where(
            late_feasible,
            late["cdi_mean"],
            np.inf,
        ).argsort()
        late_best = np.min(late["cdi_mean"][late_feasible])
        promising = late_feasible & (
            late["cdi_mean"] <= late_best + 2.5e-4
        )
        exploration_score = np.where(
            promising,
            -(late["cdi_std"] / max(np.max(late["cdi_std"]), 1.0e-12))
            - 0.25
            * (
                late["root_std"]
                / max(np.max(late["root_std"]), 1.0e-12)
            ),
            np.inf,
        )
        exploration_rank = exploration_score.argsort()
        chosen = first_distinct(
            [
                ("early_min_cdi", early_rank),
                ("early_constraint_boundary", boundary_rank),
                ("late_min_cdi", late_rank),
                ("late_uncertainty_exploration", exploration_rank),
            ],
            candidates_scaled,
        )
        prefix = "te" if concept == "trailing_edge" else "tw"

        for candidate_number, (reason, index) in enumerate(chosen, start=1):
            values = candidates[index].tolist()
            case_id = (
                f"{prefix}_b{args.batch:02d}_c{candidate_number:02d}_"
                f"{reason}"
            )
            schedule = schedule_from_iterables(
                morph["eta_start"],
                morph["eta_end"],
                morph["active_control_etas"],
                values,
                morph["fixed_inboard_boundary_value"],
            )
            design = {
                "case_id": case_id,
                "concept": concept,
                "control_etas": morph["active_control_etas"],
                "control_values": values,
                "seed_type": f"surrogate_batch_{args.batch:02d}",
                "proposal_reason": reason,
                "schedule_metrics": schedule.metrics(
                    morph["dense_constraint_points"]
                ),
            }
            if concept == "trailing_edge":
                design["x_h_over_c"] = morph["trailing_edge"]["x_h_over_c"]
                design["command_units"] = "A_over_c"
            else:
                design["rotation_axis_x_over_c"] = morph["twist"][
                    "rotation_axis_x_over_c"
                ]
                design["command_units"] = "deg"
            all_designs.append(design)

            prediction_row = {
                "case_id": case_id,
                "concept": concept,
                "proposal_reason": reason,
                **{
                    name: value
                    for name, value in zip(CONTROL_COLUMNS, values)
                },
            }
            for state in ["early_cruise", "late_cruise"]:
                prediction = state_predictions[state]
                prediction_row.update(
                    {
                        f"{state}_predicted_CDi": prediction["cdi_mean"][
                            index
                        ],
                        f"{state}_CDi_std": prediction["cdi_std"][index],
                        f"{state}_predicted_root_bending_Nm": prediction[
                            "root_mean"
                        ][index],
                        f"{state}_root_bending_std_Nm": prediction[
                            "root_std"
                        ][index],
                        f"{state}_predicted_root_utilization": prediction[
                            "root_mean"
                        ][index]
                        / root_limit,
                    }
                )
            all_predictions.append(prediction_row)

    (output / "proposed_designs.json").write_text(
        json.dumps(all_designs, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(output / "candidate_predictions.csv", all_predictions)
    write_csv(output / "surrogate_diagnostics.csv", all_diagnostics)
    print(
        f"Wrote {len(all_designs)} candidates to "
        f"{output / 'proposed_designs.json'}"
    )


if __name__ == "__main__":
    main()

