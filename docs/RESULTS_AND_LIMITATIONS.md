# Audited results and limitations

## Decision-level cruise results

The current decision table uses far-field `CDiw` and exact VSPAERO evaluations.
The root-bending limit is illustrative, not a certified structural allowable.

| Concept | Early-cruise reduction | Late-cruise reduction | Interpretation |
|---|---:|---:|---|
| Conventional hinged | see result CSV | see result CSV | mature, limited spanwise authority |
| Continuous trailing edge | 1.424% | 4.302% | strongest audited early result; essentially tied late |
| Distributed twist | 1.031% | 4.313% | broad load authority; essentially tied late |

At early cruise, the selected trailing-edge and twist cases use 99.54% and
99.99% of the illustrative root-bending limit. Small changes to that assumed
limit can reverse the ranking. The result is therefore as much a statement
about the chosen allowable as it is about aerodynamic concept quality.

At late cruise, the difference between trailing-edge camber and twist is only
0.001 percentage points in drag reduction. This is not a defensible basis for
hardware down-selection.

## Corrected low-speed results

At Mach 0.10 and fixed `CL = 0.428277635108`, relative to the corrected rigid
wing:

| Concept | `CDiw` reduction | Improvement |
|---|---:|---:|
| Conventional hinged | 0.520% | 0.295 drag counts |
| Continuous trailing edge | 1.705% | 0.966 drag counts |
| Distributed twist | 1.502% | 0.851 drag counts |

The trailing-edge/twist gap is 0.115 drag counts. The collaborator's matched-mesh
RANS workflow reported a useful resolvable delta of about 0.35 counts, so it
cannot separate these concepts at low speed either.

## Evidence volume

- Corrected cruise comparison: 102 explicit geometries, 204 operating-point
  evaluations, and 816 native solver files in the archival workspace.
- Corrected low-speed comparison: 118 explicit geometries across rigid,
  conventional, trailing-edge, and twist concepts.
- Representative geometries and summary tables are retained here; the full
  calculation database remains in the project archive.

## RANS status at handover

The delivered baseline RANS case was at Mach 0.10 and matched the low-speed
condition. It found close agreement in root bending and lift centroid, while
span efficiency differed because induced-drag extraction is sensitive to wake
plane position. It also supplied a pressure-integrated local hinge moment about
the swept `x_h/c = 0.62` line over `0.60 <= eta <= 1.00`.

That local hinge moment is model-scale and low-speed. It must not be used for
actuator sizing at cruise. Collaborator RANS files are not redistributed here.

## What the results do not prove

- They do not resolve shock/boundary-layer effects at Mach 0.78.
- They do not include aeroelastic deformation or fuel relief.
- They do not quantify actuator force, stroke, energy, mass, or life.
- They do not prove that the commanded morphing shape is structurally feasible.
- They do not establish a universal winner between twist and camber.


