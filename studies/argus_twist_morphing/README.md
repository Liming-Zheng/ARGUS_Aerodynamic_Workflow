# ARGUS Distributed Twist Morphing Study

This project is an independent continuation of the ARGUS aerodynamic study.
It investigates outer-wing twist morphing while preserving the original
airfoil sections.

The previous trailing-edge camber-morphing project remains unchanged in:

`studies\argus_morphing`

## Concept

- Baseline geometry: NASA EET AR=12 OpenVSP model.
- Analysis geometry: cruise wing only.
- Morphing region: initially `0.60 <= eta <= 0.95`.
- Airfoil section shape: unchanged.
- Morphing variable: additional local twist angle.
- Nominal rotation reference: quarter-chord spar axis, `x/c = 0.25`.
- Initial study: symmetric twist for cruise efficiency and load alleviation.
- Later study: differential left/right twist for roll control.

OpenVSP's wing `Twist` parameter changes section incidence. The geometry
verification stage must confirm the actual rotation reference and spar-axis
motion before aerodynamic optimization begins.

## Audit status

The historical low-speed twist files remain valid for dimensionless
coefficients (`CL`, `CDi`) and relative comparisons formed with the twist
study's own baseline. Their absolute `N`, `N m`, displacement, and axis-moment
columns were produced before the native-foot unit audit and are withdrawn.
Do not use those columns for actuator sizing.

The authoritative dimensional twist comparison is
`argus_cruise_comparison`, where model-to-aircraft scaling, atmosphere,
required lift, and the absolute root-bending constraint are explicit. The
local actuator torque for twist is not computed by VSPAERO strip
post-processing and requires pressure integration about a defined structural
axis.

## Directory Layout

```text
argus_twist_morphing/
  config/       study definitions and OpenVSP settings
  inputs/       copied baseline geometry; never modified in place
  outputs/      generated VSP models and aerodynamic results
  plot/         figures and editable plot outputs
  scripts/      executable workflow steps
  src/          reusable twist, load, and optimization utilities
  tests/        unit tests
```

## Planned Workflow

1. Build a clean wing-only baseline from the public source model.
2. Audit OpenVSP section twist parameters and the effective rotation axis.
3. Generate representative `0`, `+/-2`, and `+/-4` degree twist cases.
4. Visualize the baseline and morphed geometries.
5. Run symmetric fixed-lift DOE cases.
6. Extract induced drag, spanwise lift, root bending, and pitching moment.
7. Add cruise-efficiency, load-alleviation, and balanced optimizations.
8. Add differential twist for roll-control analysis.
9. Compare twist morphing with the existing trailing-edge morphing results.

## Python Environments

- General analysis and plotting:
  `python`
- OpenVSP API:
  `<OPENVSP_PYTHON>`
- OpenVSP installation:
  `<OPENVSP_ROOT>`


