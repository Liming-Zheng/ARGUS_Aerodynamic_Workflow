# Contributing

## Development rules

1. Work on a branch and keep changes scoped to one study where possible.
2. Do not commit machine-local generated configs or solver `outputs/` folders.
3. Add or update tests for geometry schedules and result-processing changes.
4. Run each study's tests separately; two historical test modules share the
   same filename and can collide when collected in one pytest invocation.
5. Preserve exact case IDs and record OpenVSP version, config, and Git commit for
   any result promoted to `results/`.
6. Final rankings must come from exact solver reruns, never surrogate predictions.
7. State `CDi` versus `CDiw`, reference area, lift condition, units, and frame.
8. Do not add collaborator data without explicit redistribution permission.

## Before opening a pull request

```powershell
python -m pytest studies/argus_morphing/tests
python -m pytest studies/argus_twist_morphing/tests
python -m pytest studies/argus_corrected_cruise_comparison/tests
python -m pytest studies/argus_mach01_comparison/tests
python tools/validate_repository.py
```

For changes that invoke OpenVSP, also run one geometry-only dry run and one
fixed-lift VSPAERO case.

