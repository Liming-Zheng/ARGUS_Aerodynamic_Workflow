# ARGUS Corrected Conventional Hinged-Control Cruise Comparison

This independent post-audit project compares the corrected NASA EET AR=12
rigid wing with its original-style, two-segment low-speed aileron represented
as a symmetric zero-gap hinged trailing-edge control. It uses the same
corrected baseline geometry, physical early/late cruise states, and absolute
root-bending limit definition as `argus_corrected_cruise_comparison`.

The pre-audit project `argus_conventional_control_comparison` is retained
unchanged for traceability.

## Geometry definition

- NASA TP-1580 Figure 1(b)
- hinge: `x_h/c = 0.70`
- segment 1: `eta = 0.710 .. 0.852`
- segment 2: `eta = 0.852 .. 0.970`
- NASA mechanical authority: `+/-30 deg`
- cruise optimization authority: `+/-6.6544 deg`

The smaller optimization bound gives the same maximum trailing-edge vertical
displacement as the continuous trailing-edge study's `A/c = 0.035` limit.

The source geometry is the Tyler-audited baseline with coordinate-resampled,
linearly blended inserted airfoils. The conventional surface remains a
zero-gap outer-mold-line approximation, so real hinge-gap and viscous profile
drag are not represented by the VSPAERO comparison.

## Run order

```powershell
$py = "python"
$vspPy = "<OPENVSP_PYTHON>"

& $py scripts\01_build_study_manifest.py
& $vspPy scripts\02_run_rigid_baseline_states.py
& $py scripts\03_create_coarse_grid.py
& $vspPy scripts\04_generate_geometries.py --batch 1
& $vspPy scripts\05_evaluate_cases.py --batch 1 --workers 4
& $py scripts\06_propose_local_refinement.py
& $vspPy scripts\04_generate_geometries.py --batch 2
& $vspPy scripts\05_evaluate_cases.py --batch 2 --workers 4
```

The `.vsp3` file in each case directory is the exact geometry evaluated by
VSPAERO and can be passed to CFD.


