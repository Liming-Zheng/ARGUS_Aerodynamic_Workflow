# Extending the optimization

## Stable boundary

New optimization work should call `CoupledEvaluationPipeline.evaluate()` and
should not embed a new optimizer inside the OpenVSP or VSPAERO scripts. One call
accepts a `DesignPoint` and an `OperatingPoint` and returns a complete
`EvaluationRecord` with the objective, constraints, feasibility, discipline
metrics, file paths, and provenance.

This separation lets a researcher change the search algorithm without changing
the geometry or analysis definitions. It also lets the same optimizer operate
in aerodynamic-only or coupled aerodynamic-structural mode.

## Adding a new optimizer

1. Define variable names, bounds, and units in one configuration file.
2. Convert every optimizer vector into a named `DesignPoint`.
3. Call the pipeline once for each exact candidate.
4. Return the scalar objective and named constraints to the optimizer.
5. Cache `evaluation_record.json` by case ID; never silently overwrite an
   existing exact result.
6. Strictly rerun the selected candidate with the exact discipline models.

The feasibility convention is:

```text
g_i(x) <= 0  -> feasible
g_i(x) > 0   -> violated
```

The default objective is wake/Trefftz induced drag, `CDiw`. A custom objective
is simply a callable:

```python
def mission_objective(aero, structure):
    mass_penalty = 0.0 if structure is None else 1.0e-4 * structure.metrics["mass_kg"]
    return aero.cdiw + mass_penalty
```

Pass it as `objective_function=mission_objective` when constructing the
pipeline. For a multi-objective algorithm, read the full aerodynamic and
structural metric dictionaries from each returned record instead of collapsing
them prematurely into one weighted number.

## Adding a new morphing concept

Implement the `GeometryGenerator` protocol. The generator must create an
explicit geometry artifact and report:

- the case ID;
- the generated file path;
- the geometry length unit;
- the exact named design variables; and
- metadata identifying the source baseline and generator version.

The existing trailing-edge, twist, and hinged-control studies remain the
scientific reference implementations. A new generator should first reproduce
the rigid baseline and one known case before entering an optimization.

## Adding structural constraints

Follow [STRUCTURAL_COUPLING.md](STRUCTURAL_COUPLING.md). A structural solver may
be an imported Python object or any executable wrapped by
`ExternalCommandStructuralEvaluator`. Return normalized constraints such as:

```text
max_strain_ratio = computed_strain / allowable_strain - 1
actuator_force_ratio = required_force / available_force - 1
```

This keeps the optimizer independent of the structural solver and makes active
constraints visible in the final record.

## Choosing an algorithm

- Use a small exact design of experiments to verify a new parameterization.
- Use differential evolution or another global method when the variable count
  is modest and exact evaluations are affordable.
- Use a surrogate-assisted batch method when VSPAERO or the structural model is
  expensive.
- Use a multi-objective method only when the trade space, rather than a single
  selected design, is the intended deliverable.

Regardless of algorithm, reported optima must be exact reruns, and comparisons
must use the same operating point, geometry baseline, objective definition,
and constraint set.
