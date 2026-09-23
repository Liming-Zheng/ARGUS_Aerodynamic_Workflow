# Preliminary Distributed-Twist Morphing Results

## Status

These are strict fixed-lift VSPAERO results for five representative twist
cases. They are a DOE screening study, not yet an optimized twist schedule.

The aerodynamic working point and baseline are the same as the existing
trailing-edge morphing study:

- wing-only cruise model;
- `CL_target = 0.428277635108`;
- `Mach = 0.1`;
- morphing region `0.60 <= eta <= 0.95`;
- section rotation axis `x/c = 0.25`.

## Main Result

Distributed twist provides bidirectional control of the aerodynamic
drag--load trade-off.

| Case | CDi reduction | Root bending change | Outer-wing lift change |
|---|---:|---:|---:|
| Uniform wash-in `+2 deg` | `+3.94%` | `+5.26%` | `+15.58%` |
| Bell wash-in `+4 deg` | `+3.50%` | `+7.77%` | `+23.52%` |
| Uniform wash-out `-2 deg` | `-8.61%` | `-5.29%` | `-15.67%` |
| Bell wash-out `-4 deg` | `-15.20%` | `-7.83%` | `-23.68%` |

Positive CDi reduction means an aerodynamic improvement. Negative values mean
the induced drag increased.

## Interpretation

- Wash-in moves lift toward the outer wing. At this baseline operating point,
  this makes the spanwise loading closer to the induced-drag optimum and
  reduces CDi. The cost is higher root bending.
- Wash-out unloads the outer wing and moves lift inboard. This reduces root
  bending but increases induced drag.
- Twist morphing is therefore especially promising as a multifunctional
  control mechanism: one direction supports cruise efficiency, while the
  opposite direction supports gust or manoeuvre load alleviation.
- The existing trailing-edge preferred candidate gives `4.43%` CDi reduction
  with `6.08%` root bending increase. The representative uniform `+2 deg`
  twist case already gives `3.94%` CDi reduction with `5.26%` bending
  increase. This is not yet an optimized twist result, so a fair optimized
  comparison is justified.

## Next Evidence Required

1. Optimize five spanwise incremental-twist controls for minimum CDi.
2. Optimize the same controls for minimum root bending with a drag constraint.
3. Generate a Pareto front between CDi and root bending.
4. Add differential left/right twist and evaluate rolling and yawing moments.
5. Estimate torsional actuator work and required wing-box torque.
6. Check aeroelastic twist loss and structural compatibility.


