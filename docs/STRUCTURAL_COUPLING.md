# Structural and multidisciplinary coupling

## Purpose

The aerodynamic studies are mature enough to act as one discipline inside a
multidisciplinary optimization, but the existing VSPAERO scripts should not be
tightly coupled to one structural implementation. The stable interface added at
handover separates four responsibilities:

1. geometry generation;
2. aerodynamic evaluation;
3. structural/actuator evaluation; and
4. optimization and constraint handling.

![Coupled workflow](images/coupled_workflow.png)

## Contract for Marco's structural model

The simplest integration is an external command:

```text
python structural_model.py --input structural_request.json --output structural_result.json
```

The request contains:

- case and operating-point IDs;
- concept and design variables;
- absolute path and length unit of the generated `.vsp3` geometry;
- fixed-lift aerodynamic coefficients;
- half-wing root bending in N m;
- a path to the spanwise load table when available; and
- the requested structural and actuator outputs.

The result returns:

- structural and mechanism metrics, such as mass, stress, strain, force,
  stroke, work, and stiffness;
- normalized constraints using `g(x) <= 0` as feasible;
- an overall feasibility flag;
- optional paths to deformation fields or detailed result files; and
- metadata identifying the structural model version and assumptions.

JSON schemas are stored in `interfaces/`. The external process adapter is
`argus_workflow.ExternalCommandStructuralEvaluator`.

## Recommended first integration

Start with one selected trailing-edge case and one selected twist case at the
same operating point. Do not immediately place a costly nonlinear structural
solve inside a large optimization.

1. Verify units, axes, sign conventions, and spanwise interpolation.
2. Compare the undeformed reference geometry in both tools.
3. Exchange one aerodynamic load table and reproduce root bending.
4. Return mass, maximum strain, actuator force, and actuator stroke.
5. Add each allowable as an inequality constraint.
6. Run a small exact design of experiments.
7. Only then train coupled surrogates or launch batch optimization.

## Extending the optimizer

Alexander or another researcher can retain the same evaluation pipeline and
replace only the search strategy. An optimizer supplies a `DesignPoint` and
receives an `EvaluationRecord` containing:

- objective value, defaulting to `CDiw`;
- aerodynamic and structural metrics;
- named constraints;
- feasibility; and
- complete file provenance.

The objective function may be replaced by a mission-weighted drag, energy, or
mass objective without changing the solvers. Multi-objective optimizers can use
the full metric dictionaries directly. Final candidates must still be rerun by
the exact discipline models.

## Interface versioning

The current schema version is `1.0`. Add fields in a backward-compatible way
where possible. A breaking change must increment the major schema version and
update both JSON schemas, tests, the example solver, and this document.

## What is and is not cross-platform

The orchestration layer uses `pathlib`, argument lists, JSON, and `shell=False`
and is tested by CI on Windows, Ubuntu, and macOS. OpenVSP/VSPAERO execution was
developed and scientifically verified on Windows. Linux and macOS users must
install a matching OpenVSP release and Python bindings and should reproduce a
baseline case before comparing new results.
