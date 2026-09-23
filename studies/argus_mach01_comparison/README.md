# ARGUS Mach 0.1 Four-Concept Comparison

This study re-evaluates the existing rigid, conventional hinged, continuous
trailing-edge, and distributed-twist geometry database at Mach 0.1.

The low-speed point is a **fixed-CL method-sensitivity case**, not an A320
weight-supporting flight condition:

- Mach number: 0.1
- ISA altitude: 0 m
- target CL: 0.529297087 (the existing early-cruise target)
- objective: minimum VSPAERO induced-drag coefficient, CDi
- load constraint: half-wing root bending no greater than the Mach 0.1 rigid
  baseline; final selection uses the strict inequality without positive
  feasibility tolerance

Using the same target CL and the same saved geometries isolates the effect of
the VSPAERO Mach setting. Dimensional loads are reported for the explicitly
defined sea-level dynamic pressure, but the decision plots emphasize
dimensionless coefficients and root-bending utilization.

## Run

```powershell
$py = "<OPENVSP_PYTHON>"
& $py scripts\01_run_mach01_database.py --workers 1
& "python" scripts\02_summarize_and_plot.py
```

For the local exact-search refinement used by the final result:

```powershell
$general = "python"
& $general scripts\03_create_local_refinement.py
& $py ..\argus_cruise_comparison\scripts\04_generate_seed_geometries.py `
  --project ..\argus_cruise_comparison `
  --cases outputs\refinement_designs\local_refinement_designs.json `
  --output-root outputs\refinement_geometries
& $py scripts\01_run_mach01_database.py --workers 1
& $general scripts\02_summarize_and_plot.py
```

OpenVSP/VSPAERO is kept serial by default because simultaneous Python API
processes have previously competed for OpenVSP temporary files on this
machine. Completed cases are cached and may be resumed.


