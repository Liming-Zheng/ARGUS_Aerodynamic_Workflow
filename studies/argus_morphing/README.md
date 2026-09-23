# ARGUS morphing-wing aerodynamic workflow

This project turns the earlier OpenVSP experiment into a reproducible wing-only
baseline, morphing DOE, and candidate-load evaluation pipeline.

## Audit status

The authoritative decision-level study is the early/late-cruise workflow in
`argus_cruise_comparison`. Run the repository audit before quoting results:

```powershell
python ..\audit\scripts\01_run_full_report_audit.py `
  --repo-root .. `
  --report-root <REPORT_ROOT>
```

The scripts numbered `01` through `14`, `16`, `17`, and `19` through `24`
document the historical method-development sequence. Outputs containing
`hinge_torque_proxy_Nm`, `hinge_moment_proxy`, or the source-less
`1050 N m` limit must not be used for actuator sizing. The audited low-speed
trailing-edge candidate is `mcv2_i002_c01`; its local actuator hinge moment is
not yet available.

## Baseline conventions

- Native OpenVSP geometry units: feet. SI post-processing explicitly uses
  `0.3048 m/ft`.
- Aerodynamic model: wing-only, half-wing strip results from VSPAERO.
- Positive lift: upward aerodynamic force.
- Root bending moment: `integral(L'(y) * y dy)` for one half-wing.
- Audited low-speed dimensional condition: `rho=1.225003 kg/m^3`,
  `V=30.48 m/s` (`100 ft/s`), hence approximately `q=569.0 Pa`.
- Default comparison case: `alpha=2 deg`, `Mach=0.10`.
- Outer-wing lift fraction reported in the main metric uses `eta >= 0.60`.

The section-table leading-edge coordinates are native-foot wing-local values,
before the model's global OpenVSP rotations and translations. VSPAERO strip
coordinates are converted to SI before aerodynamic load integration.

## Run

```powershell
<OPENVSP_PYTHON> scripts\01_build_and_run_baseline.py
python scripts\02_postprocess_baseline.py
python scripts\03_check_airfoil_morphing.py
<OPENVSP_PYTHON> scripts\04_generate_representative_cases.py
<OPENVSP_PYTHON> scripts\05_run_representative_vspaero.py
<OPENVSP_PYTHON> scripts\06_trim_cases_to_target_cl.py
<OPENVSP_PYTHON> scripts\07_build_refined_baseline.py
python scripts\08_prepare_minimal_doe.py
python scripts\09_audit_minimal_doe.py
<OPENVSP_PYTHON> scripts\10_run_minimal_doe.py --workers 4
python scripts\11_summarize_minimal_doe.py
# Historical scripts after step 11 are retained for traceability.
python scripts\14_prepare_optimization_samples.py
<OPENVSP_PYTHON> scripts\04_generate_representative_cases.py --cases config\optimization_initial_samples.json --output-root outputs\optimization\samples
<OPENVSP_PYTHON> scripts\15_run_optimization_samples.py --workers 2
python scripts\18_run_user_optimization.py --dry-run
python scripts\18_run_user_optimization.py
python -m pytest tests
```

The configurable handover workflow is documented in
`OPTIMIZATION_GUIDE_CN.md`.

Override paths with command-line options when the project is moved.

The standalone airfoil check uses NASA section 4 (`eta=0.71`) by default and
generates all combinations of `x_h/c = 0.35, 0.50, 0.62` and
`A_max/c = -0.04 ... 0.04`. Positive amplitude means trailing-edge-down even
though the airfoil coordinate displacement is negative because `z` is upward.


