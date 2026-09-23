# Custom optimizer example

This folder shows the adapter pattern for connecting a search algorithm to the
ARGUS evaluation contract. The example uses a cheap in-memory aerodynamic model
so it runs on every platform without OpenVSP. It is an interface demonstration,
not an aerodynamic result.

Run from the repository root:

```bash
python examples/custom_optimizer/random_search_demo.py
```

Replace `DemoGeometryGenerator` and `DemoAerodynamicEvaluator` with the exact
ARGUS adapters for scientific work. The random-search loop itself can be
replaced by SciPy, pymoo, Optuna, or another optimizer without changing the
pipeline contract.
