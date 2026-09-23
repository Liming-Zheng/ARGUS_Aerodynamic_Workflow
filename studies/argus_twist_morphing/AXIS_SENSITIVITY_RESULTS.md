# Twist-Axis Location Sensitivity

## Study definition

The distributed-twist rotation axis was evaluated at:

- `x/c = 0.25`;
- `x/c = 0.33`;
- `x/c = 0.40`;
- `x/c = 0.50`.

For every axis, an axis-matched baseline and uniform `+2 deg` wash-in and
`-2 deg` wash-out cases were evaluated at the common fixed-lift condition:

- `CL_target = 0.428277635108`;
- `Mach = 0.1`;
- wing-only VSPAERO model;
- morphing region `0.60 <= eta <= 0.95`.

## Main aerodynamic result

The fixed-lift aerodynamic effect of axis position is very small.

| Axis | Wash-in CDi reduction | Wash-in root bending | Wash-out CDi reduction | Wash-out root bending |
|---:|---:|---:|---:|---:|
| 25% c | 3.9355% | 5.2631% | -8.6102% | -5.2932% |
| 33% c | 3.9351% | 5.2628% | -8.6048% | -5.2913% |
| 40% c | 3.9362% | 5.2613% | -8.5972% | -5.2890% |
| 50% c | 3.9420% | 5.2599% | -8.5859% | -5.2876% |

Moving the axis from 25% to 50% chord changes the wash-in induced-drag
reduction by only `0.0065 percentage points`. This is much smaller than the
effect of changing the twist schedule itself.

## Kinematic and torsional result

The axis location strongly changes the geometric travel and aerodynamic moment
about the axis.

| Axis | Maximum LE travel | Maximum TE travel | Wash-in moment proxy |
|---:|---:|---:|---:|
| 25% c | 7.18 mm | 21.53 mm | 1220 N m |
| 33% c | 9.47 mm | 19.23 mm | 1280 N m |
| 40% c | 11.48 mm | 17.22 mm | 1332 N m |
| 50% c | 14.35 mm | 14.35 mm | 1406 N m |

Moving the axis aft:

- reduces trailing-edge travel;
- increases leading-edge travel;
- increases the integrated aerodynamic torsional-moment proxy;
- gives almost no meaningful fixed-lift induced-drag advantage.

For the present wing and operating point, the aerodynamic center is close to
the quarter chord. Moving the structural rotation axis aft therefore increases
the lift moment arm.

## Engineering recommendation

The current aerodynamic evidence favors retaining an axis near `x/c = 0.25`.
An axis near `x/c = 0.33` remains a reasonable structural trade candidate if it
provides substantially better packaging, spar integration, or mechanism
geometry. The `x/c = 0.50` axis does not show enough aerodynamic benefit to
compensate for its larger leading-edge motion and higher torsional demand.

The final choice should not be based on VSPAERO alone. The next comparison
should combine:

1. optimized twist schedules at 25% and 33% chord;
2. wing-box torsional stiffness;
3. actuator torque, stroke, and mechanical advantage;
4. skin strain and section continuity;
5. aeroelastic twist loss under load.

## Modelling limitation

OpenVSP applies `Twist_Location` to the total section twist, including baseline
washout. An axis-matched baseline was therefore used for every axis so the
reported percentages isolate the incremental `+/-2 deg` twist effect. This is
appropriate for aerodynamic screening, but a CAD or structural model should
later enforce one identical undeformed baseline and the exact physical
rotation kinematics.


