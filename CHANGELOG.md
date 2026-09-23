# Changelog

## 1.1.0 - 2026-09-23

- Added a platform-neutral `argus_workflow` package with typed contracts for
  geometry, aerodynamics, structures, objectives, and constraints.
- Added a versioned JSON interface and external-command adapter for structural
  and actuator models.
- Added runnable structural-coupling and custom-optimizer examples.
- Added Windows, Ubuntu, and macOS setup guidance and a three-platform CI test
  matrix for the Python orchestration layer.
- Added multidisciplinary extension documentation and a coupled-workflow
  architecture figure for project handover.
- Published the repository under BSD-3-Clause with explicit ARGUS project
  provenance, third-party scope, and public contribution guidance.

## 1.0.0-handover - 2026-09-23

- Curated maintained geometry, optimization, comparison, and audit code from
  the ARGUS development workspace.
- Added portable runtime configuration templates and environment checks.
- Added audited `CDiw` cruise and low-speed summary tables.
- Added selected OpenVSP geometries with SHA-256 checksums.
- Documented the airfoil-interpolation correction, dimensional-unit audit,
  withdrawal of the legacy hinge proxy, and near-/far-field drag distinction.
- Excluded large intermediate solver databases and collaborator-owned RANS data.
