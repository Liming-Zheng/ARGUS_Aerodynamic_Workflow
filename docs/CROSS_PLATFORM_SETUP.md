# Cross-platform setup

The Python orchestration and coupling interface support Windows, Ubuntu, and
macOS. Numerical equivalence of OpenVSP/VSPAERO must be verified locally.

## Common requirements

- Python 3.11 or newer
- OpenVSP 3.50.1 where available, including VSPAERO and Python bindings
- Git

Clone the private repository after accepting the GitHub invitation:

```bash
git clone https://github.com/Liming-Zheng/ARGUS_Aerodynamic_Workflow.git
cd ARGUS_Aerodynamic_Workflow
```

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python tools\configure_runtime.py `
  --openvsp-root "C:\OpenVSP-3.50.1-win64" `
  --openvsp-python "C:\path\to\openvsp-python\python.exe" `
  --general-python ".\.venv\Scripts\python.exe"
```

## Ubuntu

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python tools/configure_runtime.py \
  --openvsp-root "$HOME/opt/OpenVSP-3.50.1" \
  --openvsp-python "$HOME/opt/openvsp-python/bin/python" \
  --general-python "$PWD/.venv/bin/python"
```

## macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python tools/configure_runtime.py \
  --openvsp-root "/Applications/OpenVSP.app/Contents" \
  --openvsp-python "/path/to/openvsp-python/bin/python" \
  --general-python "$PWD/.venv/bin/python"
```

The exact macOS OpenVSP application and binding paths depend on the local
installation. Do not copy the example paths blindly.

## Verification

```bash
python tools/check_environment.py
python -m pytest tests
python -m pytest studies/argus_morphing/tests
python -m pytest studies/argus_twist_morphing/tests
python -m pytest studies/argus_corrected_cruise_comparison/tests
python -m pytest studies/argus_mach01_comparison/tests
python tools/validate_repository.py
python examples/structural_coupling/run_demo.py
```

Before a scientific run on a new operating system, rerun the corrected rigid
baseline and compare `CL`, `CDiw`, span efficiency, and root bending against the
audited tables in `results/`.
