"""Reusable utilities for the user-facing ARGUS optimization loop.

The expensive function is OpenVSP/VSPAERO. A Gaussian-process surrogate is
trained on all exact samples, and a cheap inner optimizer proposes the next
batch. Exact results are always used to update convergence history.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ObjectiveDefinition:
    metric: str
    direction: str
    root_bending_weight: float
    torque_weight: float
    endpoint_weight: float
    curvature_weight: float


def validate_user_config(config: dict[str, Any]) -> None:
    required = ["design_variables", "objective", "constraints", "algorithm", "iterations"]
    missing = [name for name in required if name not in config]
    if missing:
        raise ValueError(f"Missing configuration sections: {missing}")
    bounds = config["design_variables"]["twist_bounds_deg"]
    if len(bounds) != 2 or bounds[0] >= bounds[1]:
        raise ValueError("twist_bounds_deg must be [lower, upper]")
    if config["objective"]["direction"] not in {"minimize", "maximize"}:
        raise ValueError("objective.direction must be minimize or maximize")
    if config["algorithm"]["name"] not in {"differential_evolution", "random_search"}:
        raise ValueError("algorithm.name must be differential_evolution or random_search")
    if int(config["iterations"]["max_iterations"]) < 0:
        raise ValueError("max_iterations must be non-negative")
    if int(config["iterations"]["batch_size"]) < 1:
        raise ValueError("batch_size must be positive")


def filtered_exact_samples(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return exact samples selected by optional case-id prefixes."""
    prefixes = config.get("sample_filter", {}).get("case_id_prefixes", [])
    if not prefixes:
        return rows
    selected = [
        row for row in rows
        if any(str(row.get("case_id", "")).startswith(prefix) for prefix in prefixes)
    ]
    if not selected:
        raise RuntimeError(
            "No exact samples matched sample_filter.case_id_prefixes="
            f"{prefixes}"
        )
    return selected


def objective_definition(config: dict[str, Any]) -> ObjectiveDefinition:
    section = config["objective"]
    return ObjectiveDefinition(
        metric=section["metric"],
        direction=section["direction"],
        root_bending_weight=float(section.get("root_bending_weight", 0.0)),
        torque_weight=float(section.get("torque_weight", 0.0)),
        endpoint_weight=float(section.get("endpoint_weight", 0.0)),
        curvature_weight=float(section.get("curvature_weight", 0.0)),
    )


def control_values(row: dict[str, Any]) -> np.ndarray:
    def control_index(name: str) -> int | None:
        if not (name.startswith("T") and name.endswith("_deg")):
            return None
        stem = name[1:name.index("_")]
        return int(stem) if stem.isdigit() else None

    names = sorted(
        (name for name in row if control_index(name) is not None),
        key=lambda name: control_index(name) or 0,
    )
    return np.asarray([float(row[name]) for name in names], dtype=float)


def include_boundary_zeros(config: dict[str, Any]) -> bool:
    return bool(
        config.get("design_variables", {}).get(
            "include_root_boundary_zero_in_adjacent_delta",
            False,
        )
    )


def adjacent_deltas(values: np.ndarray, include_boundaries: bool = False) -> np.ndarray:
    if include_boundaries:
        values = np.concatenate(([0.0], values))
    return np.abs(np.diff(values))


def max_adjacent_delta_for_row(row: dict[str, Any], config: dict[str, Any]) -> float:
    values = control_values(row)
    if values.size:
        deltas = adjacent_deltas(values, include_boundary_zeros(config))
        return float(np.max(deltas)) if deltas.size else 0.0
    return float(row["max_adjacent_twist_delta_deg"])


def shape_penalty(values: np.ndarray, definition: ObjectiveDefinition) -> float:
    if values.size == 0:
        return 0.0
    endpoint = float(values[0] ** 2 + values[-1] ** 2)
    if values.size >= 3:
        curvature = float(np.sum(np.diff(values, n=2) ** 2))
    else:
        curvature = 0.0
    return (
        definition.endpoint_weight * endpoint
        + definition.curvature_weight * curvature
    )


def exact_objective(row: dict[str, Any], definition: ObjectiveDefinition) -> float:
    """Return a scalar exact objective; lower is always better internally."""
    metric = float(row[definition.metric])
    if definition.direction == "maximize":
        metric = -metric
    bending = max(0.0, float(row["root_bending_increase_percent"]))
    torque = abs(float(row.get("hinge_torque_proxy_Nm", 0.0)))
    return (
        metric
        + definition.root_bending_weight * bending / 1000.0
        + definition.torque_weight * torque / 1.0e6
        + shape_penalty(control_values(row), definition)
    )


def is_feasible(row: dict[str, Any], config: dict[str, Any]) -> bool:
    constraints = config["constraints"]
    if constraints["root_bending"]["enabled"]:
        if float(row["root_bending_increase_percent"]) > float(
            constraints["root_bending"]["maximum_percent"]
        ):
            return False
    if constraints.get("hinge_torque_proxy", {}).get("enabled", False):
        if abs(float(row["hinge_torque_proxy_Nm"])) > float(
            constraints["hinge_torque_proxy"]["maximum_abs_Nm"]
        ):
            return False
    if max_adjacent_delta_for_row(row, config) > float(
        config["design_variables"]["max_adjacent_twist_delta_deg"]
    ):
        return False
    return True


class GaussianProcessSurrogate:
    """Scaled Gaussian-process regression with prediction uncertainty."""

    def __init__(self, x: np.ndarray, y: np.ndarray, seed: int, restarts: int):
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import (
            ConstantKernel,
            Matern,
            WhiteKernel,
        )
        from sklearn.preprocessing import StandardScaler

        self.x_scaler = StandardScaler().fit(x)
        self.y_scaler = StandardScaler().fit(y.reshape(-1, 1))
        kernel = (
            ConstantKernel(1.0, (0.05, 20.0))
            * Matern(
                length_scale=np.ones(x.shape[1]),
                length_scale_bounds=(0.05, 20.0),
                nu=2.5,
            )
            + WhiteKernel(
                noise_level=1.0e-5,
                noise_level_bounds=(1.0e-8, 0.05),
            )
        )
        self.model = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=restarts,
            random_state=seed,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            self.model.fit(
                self.x_scaler.transform(x),
                self.y_scaler.transform(y.reshape(-1, 1)).ravel(),
            )

    def predict(self, x: np.ndarray, return_std: bool = False):
        array = np.atleast_2d(x)
        transformed = self.x_scaler.transform(array)
        if not return_std:
            mean = self.model.predict(transformed)
            return self.y_scaler.inverse_transform(mean.reshape(-1, 1)).ravel()
        mean, sigma = self.model.predict(transformed, return_std=True)
        mean = self.y_scaler.inverse_transform(mean.reshape(-1, 1)).ravel()
        return mean, sigma * self.y_scaler.scale_[0]


def fit_models(rows: list[dict[str, Any]], config: dict[str, Any]):
    control_count = len(config["design_variables"]["control_etas"])
    x = np.asarray([
        [float(row[f"T{index}_deg"]) for index in range(1, control_count + 1)]
        for row in rows
    ])
    definition = objective_definition(config)
    objective_values = np.asarray([exact_objective(row, definition) for row in rows])
    bending = np.asarray([float(row["root_bending_increase_percent"]) for row in rows])
    torque_constraint_enabled = bool(
        config["constraints"].get("hinge_torque_proxy", {}).get("enabled", False)
    )
    torque = np.asarray([
        float(row.get("hinge_torque_proxy_Nm", 0.0)) for row in rows
    ])
    seed = int(config["random_seed"])
    restarts = int(config["surrogate"]["optimizer_restarts"])
    return (
        GaussianProcessSurrogate(x, objective_values, seed, restarts),
        GaussianProcessSurrogate(x, bending, seed + 1, restarts),
        (
            GaussianProcessSurrogate(x, torque, seed + 2, restarts)
            if torque_constraint_enabled
            else None
        ),
    )


def _candidate_score(values, models, config, selected):
    objective_model, bending_model, torque_model = models
    mean, sigma = objective_model.predict(values, return_std=True)
    score = float(mean[0]) - float(config["surrogate"]["exploration_weight"]) * float(sigma[0])
    score += shape_penalty(np.asarray(values), objective_definition(config))
    differences = adjacent_deltas(np.asarray(values), include_boundary_zeros(config))
    maximum_delta = float(
        config["design_variables"]["max_adjacent_twist_delta_deg"]
    )
    score += 1.0e5 * float(np.sum(np.maximum(differences - maximum_delta, 0.0) ** 2))
    constraints = config["constraints"]
    bending = float(bending_model.predict(values)[0])
    torque = (
        abs(float(torque_model.predict(values)[0]))
        if torque_model is not None
        else 0.0
    )
    if constraints["root_bending"]["enabled"]:
        excess = max(0.0, bending - float(constraints["root_bending"]["maximum_percent"]))
        score += float(constraints["root_bending"]["penalty"]) * excess**2
    if constraints.get("hinge_torque_proxy", {}).get("enabled", False):
        excess = max(
            0.0,
            torque - float(constraints["hinge_torque_proxy"]["maximum_abs_Nm"]),
        )
        score += float(constraints["hinge_torque_proxy"]["penalty"]) * excess**2
    minimum_distance = float(config["algorithm"]["minimum_candidate_distance"])
    for previous in selected:
        distance = float(np.linalg.norm(np.asarray(values) - np.asarray(previous)))
        score += 10.0 * max(0.0, minimum_distance - distance) ** 2
    return score


def propose_batch(models, config: dict[str, Any], iteration: int) -> list[list[float]]:
    """Propose one batch using the algorithm selected in the JSON config."""
    from scipy.optimize import differential_evolution

    lower, upper = map(float, config["design_variables"]["twist_bounds_deg"])
    dimension = len(config["design_variables"]["control_etas"])
    batch_size = int(config["iterations"]["batch_size"])
    seed = int(config["random_seed"]) + 1000 * iteration
    selected: list[list[float]] = []
    for batch_index in range(batch_size):
        local_seed = seed + batch_index
        if config["algorithm"]["name"] == "differential_evolution":
            result = differential_evolution(
                lambda values: _candidate_score(values, models, config, selected),
                bounds=[(lower, upper)] * dimension,
                seed=local_seed,
                popsize=int(config["algorithm"]["population_size"]),
                maxiter=int(config["algorithm"]["inner_max_iterations"]),
                tol=float(config["algorithm"]["tolerance"]),
                polish=bool(config["algorithm"]["polish"]),
            )
            values = result.x.tolist()
        else:
            rng = np.random.default_rng(local_seed)
            population = rng.uniform(
                lower,
                upper,
                size=(int(config["algorithm"]["random_search_samples"]), dimension),
            )
            scores = [
                _candidate_score(values, models, config, selected)
                for values in population
            ]
            values = population[int(np.argmin(scores))].tolist()
        selected.append(values)
    return selected

