# ARGUS Twist-Morphing Project Status

Date: 10 June 2026

## Isolation

This project was created as a separate sibling of the existing trailing-edge
camber-morphing project. No files were deleted or modified in the original
project.

- Existing project:
  `studies\argus_morphing`
- New project:
  `studies\argus_twist_morphing`

## Reused Components

The following components were copied and can now evolve independently:

- wing-only baseline builder;
- refined baseline builder;
- spanwise load-integration utilities;
- load-metric unit tests.

Trailing-edge airfoil-deformation code and previous optimization results were
not copied into the new project.

## Twist Parameter Audit

The source model contains nine cruise-wing sections. OpenVSP exposes both:

- section `Twist`;
- section `Twist_Location`.

The audited `Twist_Location` is `0.25` for every section, matching the proposed
quarter-chord spar axis.

The original baseline twist varies from `0 deg` at the root to approximately
`-4.115 deg` at the tip. New morphing designs must therefore apply an
**incremental twist** on top of the baseline twist, not replace the baseline
distribution.

Audit outputs:

`outputs\twist_parameter_audit\section_twist_parameter_audit.csv`

`outputs\twist_parameter_audit\twist_parameter_audit_summary.json`

## Refined Geometry

The cruise wing was refined from 9 to 19 sections. Eleven geometric sections
now lie in the intended morphing region `0.60 <= eta <= 0.95`.

The refinement preserves:

- planform;
- airfoil coordinates;
- chord distribution;
- baseline twist distribution;
- quarter-chord reference axis.

The refined model is:

`outputs\refined_baseline\baseline_wing_only_refined.vsp3`

## Fixed-CL Screening Results

Five strict fixed-lift cases were completed at:

- `CL_target = 0.428277635108`;
- `Mach = 0.1`;
- wing-only configuration.

The study is a representative DOE, not yet a numerical optimization.

| Case | CDi reduction | Root bending change | Outer-wing lift change |
|---|---:|---:|---:|
| Uniform wash-in `+2 deg` | `+3.94%` | `+5.26%` | `+15.58%` |
| Bell wash-in `+4 deg` | `+3.50%` | `+7.77%` | `+23.52%` |
| Uniform wash-out `-2 deg` | `-8.61%` | `-5.29%` | `-15.67%` |
| Bell wash-out `-4 deg` | `-15.20%` | `-7.83%` | `-23.68%` |

Positive CDi reduction denotes an aerodynamic improvement. The results show
bidirectional drag-load control: wash-in improves cruise induced drag but
raises root bending, while wash-out unloads the outer wing at a drag penalty.

The unoptimized uniform `+2 deg` case is already close to the optimized
trailing-edge preferred candidate:

- distributed twist: `3.94%` CDi reduction, `5.26%` bending increase;
- trailing-edge candidate: `4.43%` CDi reduction, `6.08%` bending increase.

Summary data:

`outputs\fixed_cl_doe\fixed_cl_twist_doe_summary.csv`

## Figures

Editable PDF and SVG figures, with PNG previews, are stored in:

`plot\twist_doe`

The four principal figures show:

1. representative incremental-twist schedules;
2. aerodynamic and load metric comparison;
3. twist versus trailing-edge drag-load trade-off;
4. spanwise load redistribution.

## Report Integration

The distributed-twist study was added to the main project report as:

`<REPORT_ROOT>\sections\12_distributed_twist_morphing.tex`

The report describes the geometry, fixed-CL method, screening results,
comparison with trailing-edge morphing, limitations, and required next steps.

## Next Technical Step

The chordwise rotation-axis sensitivity study is complete for:

- `x/c = 0.25`;
- `x/c = 0.33`;
- `x/c = 0.40`;
- `x/c = 0.50`.

At fixed lift, moving the axis has almost no effect on the aerodynamic
drag-load trade-off. For uniform `+2 deg` wash-in, CDi reduction changes only
from `3.9355%` at 25% chord to `3.9420%` at 50% chord.

The structural proxies are more sensitive:

- maximum leading-edge travel increases from `7.18 mm` to `14.35 mm`;
- maximum trailing-edge travel decreases from `21.53 mm` to `14.35 mm`;
- wash-in aerodynamic moment proxy increases from about `1220 N m` to
  `1406 N m`.

Current recommendation: retain `x/c = 0.25` as the aerodynamic reference and
carry `x/c = 0.33` as a structural trade candidate.

Detailed results:

`AXIS_SENSITIVITY_RESULTS.md`

The next technical phase should implement five smooth spanwise twist controls
and run:

1. minimum-CDi optimization with bending and smoothness constraints;
2. minimum-root-bending optimization with a drag constraint;
3. a matched CDi/root-bending Pareto study;
4. differential left/right twist cases for roll-control authority;
5. structural and aeroelastic post-processing for torsional actuator sizing.


