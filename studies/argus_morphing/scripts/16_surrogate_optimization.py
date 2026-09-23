from __future__ import annotations

import argparse
import csv
import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import differential_evolution
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.preprocessing import StandardScaler


PROJECT = Path(__file__).resolve().parents[1]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--seed", type=int, default=20260609)
    return parser.parse_args()


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_figure(fig, output, name):
    fig.savefig(output / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(output / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


class Surrogate:
    def __init__(self, x, y, seed):
        self.x_scaler = StandardScaler().fit(x)
        self.y_scaler = StandardScaler().fit(y.reshape(-1, 1))
        kernel = (
            ConstantKernel(1.0, (0.05, 20.0))
            * Matern(length_scale=np.ones(x.shape[1]), length_scale_bounds=(0.05, 20.0), nu=2.5)
            + WhiteKernel(noise_level=1.0e-5, noise_level_bounds=(1.0e-8, 0.05))
        )
        self.model = GaussianProcessRegressor(
            kernel=kernel,
            normalize_y=False,
            n_restarts_optimizer=5,
            random_state=seed,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            self.model.fit(
                self.x_scaler.transform(x),
                self.y_scaler.transform(y.reshape(-1, 1)).ravel(),
            )

    def predict(self, x, std=False):
        array = np.atleast_2d(x)
        if std:
            mean, sigma = self.model.predict(self.x_scaler.transform(array), return_std=True)
            mean = self.y_scaler.inverse_transform(mean.reshape(-1, 1)).ravel()
            sigma = sigma * self.y_scaler.scale_[0]
            return mean, sigma
        mean = self.model.predict(self.x_scaler.transform(array))
        return self.y_scaler.inverse_transform(mean.reshape(-1, 1)).ravel()


def geometric_penalty(values, max_delta=0.02):
    excess = np.maximum(np.abs(np.diff(values)) - max_delta, 0.0)
    return 1.0e5 * float(np.sum(excess**2))


def optimize_candidate(name, models, bending_limit, torque_limit, seed, bending_weight=0.0):
    cdi_model, bending_model, torque_model = models

    def objective(values):
        cdi = cdi_model.predict(values)[0]
        bending = bending_model.predict(values)[0]
        torque = abs(torque_model.predict(values)[0])
        penalty = geometric_penalty(values)
        penalty += 100.0 * max(0.0, bending - bending_limit) ** 2
        penalty += 1.0e-4 * max(0.0, torque - torque_limit) ** 2
        return cdi + bending_weight * max(bending, 0.0) / 1000.0 + penalty

    result = differential_evolution(
        objective,
        bounds=[(0.0, 0.04)] * 5,
        seed=seed,
        popsize=20,
        maxiter=250,
        polish=True,
        tol=1.0e-8,
    )
    values = result.x
    cdi_mean, cdi_std = cdi_model.predict(values, std=True)
    bending_mean, bending_std = bending_model.predict(values, std=True)
    torque_mean, torque_std = torque_model.predict(values, std=True)
    return {
        "candidate_name": name,
        **{f"A{i+1}_over_c": float(value) for i, value in enumerate(values)},
        "predicted_CDi": float(cdi_mean[0]),
        "predicted_CDi_std": float(cdi_std[0]),
        "predicted_root_bending_increase_percent": float(bending_mean[0]),
        "predicted_root_bending_std": float(bending_std[0]),
        "predicted_hinge_torque_proxy_Nm": float(torque_mean[0]),
        "predicted_hinge_torque_std_Nm": float(torque_std[0]),
        "bending_limit_percent": bending_limit,
        "torque_limit_Nm": torque_limit,
        "optimizer_success": bool(result.success),
    }


def nondominated(cdi, bending):
    order = np.argsort(cdi)
    selected = []
    best_bending = float("inf")
    for index in order:
        if bending[index] < best_bending:
            selected.append(index)
            best_bending = bending[index]
    return np.asarray(selected, dtype=int)


def main():
    args = parse_args()
    output = args.project / "outputs" / "optimization"
    rows = read_csv(output / "optimization_samples.csv")
    x = np.asarray([
        [float(row[f"A{i}_over_c"]) for i in range(1, 6)]
        for row in rows
    ])
    cdi = np.asarray([float(row["CDi"]) for row in rows])
    bending = np.asarray([float(row["root_bending_increase_percent"]) for row in rows])
    torque = np.asarray([float(row["hinge_torque_proxy_Nm"]) for row in rows])
    models = (
        Surrogate(x, cdi, args.seed),
        Surrogate(x, bending, args.seed + 1),
        Surrogate(x, torque, args.seed + 2),
    )
    candidates = [
        optimize_candidate("minimum_drag", models, 7.0, 1100.0, args.seed),
        optimize_candidate("balanced", models, 7.0, 1050.0, args.seed + 10, bending_weight=0.02),
        optimize_candidate("conservative", models, 5.0, 1000.0, args.seed + 20, bending_weight=0.04),
    ]
    write_csv(output / "surrogate_candidates.csv", candidates)

    control_etas = [0.60, 0.6875, 0.775, 0.8625, 0.95]
    designs = []
    for index, row in enumerate(candidates, start=1):
        amplitudes = [row[f"A{i}_over_c"] for i in range(1, 6)]
        designs.append({
            "case_id": f"opt_c{index:03d}",
            "candidate_name": row["candidate_name"],
            "eta_start": 0.60,
            "eta_end": 0.95,
            "x_h_over_c": 0.62,
            "A_max_over_c": max(amplitudes),
            "shape_type": "control_points",
            "control_etas": control_etas,
            "control_amplitudes_over_c": amplitudes,
            "max_adjacent_delta": max(abs(right - left) for left, right in zip(amplitudes, amplitudes[1:])),
            "max_spanwise_slope": max(abs(right - left) / 0.0875 for left, right in zip(amplitudes, amplitudes[1:])),
            "alpha_deg": 2.0,
            "mach": 0.10,
            "notes": f"Surrogate candidate: {row['candidate_name']}",
        })
    (args.project / "config" / "optimization_candidate_cases.json").write_text(
        json.dumps(designs, indent=2) + "\n", encoding="utf-8"
    )

    rng = np.random.default_rng(args.seed)
    random_x = rng.uniform(0.0, 0.04, size=(150000, 5))
    smooth = np.max(np.abs(np.diff(random_x, axis=1)), axis=1) <= 0.02
    random_x = random_x[smooth]
    pred_cdi = models[0].predict(random_x)
    pred_bending = models[1].predict(random_x)
    pred_torque = models[2].predict(random_x)
    feasible = (pred_bending <= 7.0) & (np.abs(pred_torque) <= 1100.0)
    random_x = random_x[feasible]
    pred_cdi = pred_cdi[feasible]
    pred_bending = pred_bending[feasible]
    pareto = nondominated(pred_cdi, pred_bending)
    pareto_rows = []
    for index in pareto:
        pareto_rows.append({
            **{f"A{i+1}_over_c": random_x[index, i] for i in range(5)},
            "predicted_CDi": pred_cdi[index],
            "predicted_root_bending_increase_percent": pred_bending[index],
        })
    write_csv(output / "predicted_pareto_front.csv", pareto_rows)

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    ax.scatter(bending, cdi, color="#174A6B", s=45, label="VSPAERO samples")
    ax.scatter(pred_bending[pareto], pred_cdi[pareto], color="#A8C8B0", s=12, label="Predicted Pareto front")
    for index, row in enumerate(candidates, start=1):
        ax.scatter(
            row["predicted_root_bending_increase_percent"],
            row["predicted_CDi"],
            s=90,
            marker="*",
            label=f"Candidate {index}: {row['candidate_name']}",
        )
    ax.axvline(7.0, color="#C56A32", ls="--", label="7% bending limit")
    ax.set_xlabel("Root bending increase [%]")
    ax.set_ylabel("CDi at fixed CL")
    ax.set_title("ARGUS first surrogate-assisted optimization")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    save_figure(fig, output, "surrogate_pareto_front")

    fig, ax = plt.subplots(figsize=(9, 5.2))
    for index, row in enumerate(candidates, start=1):
        values = [row[f"A{i}_over_c"] for i in range(1, 6)]
        ax.plot(control_etas, values, marker="o", lw=2, label=f"Candidate {index}: {row['candidate_name']}")
    ax.set_xlabel("eta = y/(b/2)")
    ax.set_ylabel("A(eta)/c")
    ax.set_title("Surrogate-selected spanwise morphing schedules")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    save_figure(fig, output, "surrogate_candidate_schedules")
    print(f"Created {len(candidates)} surrogate candidates")


if __name__ == "__main__":
    main()

