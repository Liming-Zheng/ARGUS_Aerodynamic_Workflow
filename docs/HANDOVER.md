# Handover guide

## Recommended reading order

1. Root `README.md` for scope, conclusions, and setup.
2. `METHODOLOGY.md` for the common workflow and optimization logic.
3. `RESULTS_AND_LIMITATIONS.md` for the audited result set.
4. `AUDIT_AND_CORRECTIONS.md` before reusing any legacy output.
5. The README in the specific study being extended.

## Which study should I modify?

| Task | Study folder |
|---|---|
| Change continuous trailing-edge parameterization | `trailing_edge_morphing` |
| Change distributed-twist parameterization | `twist_morphing` |
| Change segmented hinged controls | `conventional_control` |
| Compare morphing concepts at early/late cruise | `corrected_cruise_comparison` |
| Re-run the conventional cruise reference | `corrected_conventional_cruise` |
| Compare all concepts at Mach 0.10 | `low_speed_four_concept` |
| Re-run consistency checks | `report_audit` |

## Safe continuation workflow

1. Create a feature branch.
2. Generate local configs with `tools/configure_runtime.py`.
3. Run unit tests and a geometry-only dry run.
4. Inspect the generated `.vsp3` in OpenVSP.
5. Run one fixed-lift VSPAERO case and verify `CL` convergence.
6. Run a small seed set before launching batch optimization.
7. Rank candidates with `CDiw` and apply constraints as inequalities.
8. Strictly rerun the selected candidate and preserve its native files.
9. Record the case ID, config, solver version, and Git commit.

Never select a final design from surrogate predictions alone.

## Archived material not copied here

The original project workspace contains full seed/refinement databases, native
VSPAERO output for hundreds of cases, OCR extraction, presentation-generation
tools, report sources, and collaboration packages. These were excluded because
they are large, historical, or have separate redistribution constraints.

The full final workspace remains in the TU Delft project archive. Treat that
archive as provenance only; no code in this repository depends on its drive
letter or workstation path.

## Final maintainer checklist

- Confirm OpenVSP version before comparing numerical deltas.
- Keep low-speed and cruise tables separate.
- State whether `CDi` or `CDiw` is used; current final ranking uses `CDiw`.
- State the exact dimensional lift and atmosphere for cruise cases.
- Label the root-bending allowable as illustrative until structure supplies one.
- Obtain a pressure-integrated local hinge moment before actuator sizing.
- Preserve native `.lod`, `.polar`, `.history`, `.vspaero`, trim traces, and
  geometry checksums for any new selected candidate.

