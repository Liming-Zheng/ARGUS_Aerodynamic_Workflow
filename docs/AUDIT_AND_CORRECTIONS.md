# Audit and corrections

This document prevents known early-project issues from re-entering future work.

## Airfoil interpolation

Earlier inserted sections inherited coordinates from an outboard neighbouring
section. Chord and twist interpolation were correct, but the airfoil coordinate
arrays were not blended between the bracketing profiles. The corrected geometry
pipeline interpolates compatible section shapes and records fingerprints in
`inputs/geometry/airfoil_interpolation_audit.json`.

Use `inputs/geometry/baseline_corrected.vsp3` for current work.

## Dimensional units

Legacy scripts converted aerodynamic forces to SI while some geometry arms
remained in feet. This produced moment/displacement columns with incorrect SI
labels. Dimensionless coefficients were unaffected. Current audited result
tables either recompute dimensional quantities consistently or omit ambiguous
legacy columns.

## Hinge-moment definition

The legacy column called `morph_region_hinge_torque_proxy_Nm` was not a local
hinge moment about the morphing start line. It was effectively a morph-region
lift moment about the aircraft reference and retained feet-based arms. The
associated 1050 N m limit was illustrative and not traceable to an actuator or
skin allowable.

Consequences:

- the 1050 N m constraint is withdrawn;
- `mbr_c01_l011` is retained only as a historical result;
- actuator sizing must use pressure integration aft of the local swept hinge
  line, with frame, sign, span range, and units stated explicitly.

## Induced-drag metric

Initial optimization and plots emphasized VSPAERO near-field `CDi`. The final
audit found that the intended concept ranking is better represented by wake-plane
`CDiw`, with convergence checked against wake refinement. The trusted result
tables in this repository use `CDiw`.

## Morphing extent and variables

Final engineering studies use `0.60 <= eta <= 1.00`. Five optimization control
points define a continuous command schedule; this is distinct from the larger
number of OpenVSP geometric sections used to represent the surface.

## Objective and constraints

The final mathematical formulation minimizes induced drag only. Root bending
and command smoothness are inequality constraints. Feasible values below a limit
are not penalized in the objective. Virtual endpoint controls handle schedule
continuity where applicable.


