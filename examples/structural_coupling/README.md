# Structural-coupling example

This example shows the contract that a structural model must implement. The
included solver is deliberately non-physical and exists only to test data flow.

```bash
python -m pip install -e .
python examples/structural_coupling/run_demo.py
```

The adapter writes `structural_request.json`, calls the external program without
a platform-specific shell, and reads `structural_result.json`. Replace
`mock_structural_solver.py` with Marco's model while preserving the command-line
and JSON contracts.

All constraints use `g(x) <= 0` for feasibility. A result must state units in
metric names or metadata and must return the same case and operating-point IDs
as the request.
