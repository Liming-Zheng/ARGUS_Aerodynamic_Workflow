# Methodology

## Reference geometry

The baseline is the cruise wing from the public NASA EET high-aspect-ratio
transport model. The aspect-ratio-12 model has a 12 ft model span, 12 ft2
reference area, approximately 27 degree quarter-chord sweep, and spanwise-varying
supercritical airfoils. The source wind-tunnel report is NASA TP-1580, NTRS
record `19820007142`.

Only the wing is analyzed. Fuselage, tail, nacelles, slats, and high-lift devices
are excluded so that changes are attributable to the outer-wing concept.

## Geometry concepts

The main engineering studies use the outer-wing interval
`0.60 <= eta <= 1.00`, where `eta = y/(b/2)`.

### Continuous trailing-edge camber

Five spanwise control amplitudes define a continuous schedule. Deformation starts
at `x_h/c = 0.62` and increases smoothly toward the trailing edge using a cubic
smooth-step law. The airfoil nose and spar-side region remain unchanged.

### Distributed twist

Five spanwise twist commands rotate outer-wing sections about a local chordwise
axis. The nominal axis is `x/c = 0.25`; axis-location sensitivity was evaluated
separately. Each section retains its airfoil shape.

### Conventional hinged control

The conventional reference uses segmented control-surface deflection over the
NASA aileron region. It provides a mature but lower-spanwise-authority benchmark.

## Operating points

Two physical cruise states are used at Mach 0.78:

| State | Aircraft mass used as lift equivalent | Altitude | Target quantity |
|---|---:|---:|---|
| Early cruise | 74,500 kg | 10,000 m | dimensional lift |
| Late cruise | 56,000 kg | 12,000 m | dimensional lift |

The required `CL` follows from the atmosphere, speed, reference area, and target
lift. Each geometry is trimmed independently.

A separate corrected low-speed comparison uses Mach 0.10 and
`CL = 0.428277635108`. It supports NASA/OpenVSP/RANS consistency checks, not
full-scale cruise sizing.

## Optimization loop

1. Parameterize five spanwise commands.
2. Generate an explicit OpenVSP geometry.
3. Trim VSPAERO to fixed lift.
4. Extract far-field induced drag, spanwise loads, and root bending.
5. Reject candidates violating inequality constraints.
6. Fit surrogate models to exact evaluated cases.
7. Propose a small batch of improvement, boundary, and exploration cases.
8. Evaluate that batch with VSPAERO.
9. Strictly rerun the selected candidate.

The objective is pure induced-drag minimization. Loads and smoothness are
constraints, not weighted objective terms. The engineering cruise comparison
uses `CDiw`, the wake-plane/far-field induced-drag coefficient.

## Verification

- Unit tests cover geometry schedules and optimization utilities.
- Every selected design exists as an explicit `.vsp3` file.
- Final choices use exact VSPAERO reruns, not surrogate estimates.
- A full-wing unconstrained trailing-edge study moved the loading toward the
  analytical elliptical distribution, serving as a workflow sanity check.
- The final audit compared near-field and far-field drag, refined the wake, and
  corrected inserted-airfoil interpolation.


