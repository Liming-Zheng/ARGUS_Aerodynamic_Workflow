# ARGUS numerical audit

`scripts/01_run_full_report_audit.py` checks the saved exact aerodynamic
results against the numerical claims used by the report.

It independently:

- recomputes the early/late ISA flight states and target lift coefficients;
- reselects the minimum-`CDi` feasible candidate from every saved exact case;
- recomputes all reported induced-drag reductions;
- reintegrates representative spanwise strip loads and root bending moments;
- checks the whole-wing elliptical-loading sanity result;
- checks that critical corrected statements are present in the report; and
- inventories legacy unit labels and the withdrawn hinge-moment proxy.

Run from the `codex_work` repository root:

```powershell
python audit\scripts\01_run_full_report_audit.py `
  --report-root <REPORT_ROOT>
```

The output report distinguishes failures from residual warnings. Passing this
audit proves internal traceability of saved results; it is not an independent
CFD or experimental validation.

`outputs/solver_rerun_summaries` contains compact archived summaries from
three isolated VSPAERO reruns. The large temporary solver directories are
ignored by Git.


