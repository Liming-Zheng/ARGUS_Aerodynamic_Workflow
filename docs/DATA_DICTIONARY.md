# Core data dictionary

| Quantity | Meaning | Unit / normalization | Notes |
|---|---|---|---|
| `eta` | semi-span coordinate, `y/(b/2)` | dimensionless | 0 root, 1 tip |
| `x_h/c` | local chordwise morphing start or hinge line | dimensionless | nominal TE value 0.62 |
| `CL` | lift coefficient | `L/(q Sref)` | full-wing reference convention |
| `CDi` | VSPAERO near-field induced drag | dimensionless | historical diagnostic, not final ranking metric |
| `CDiw` | wake-plane/far-field induced drag | dimensionless | final ranking metric |
| `e` | span efficiency | dimensionless | depends on induced-drag extraction convention |
| `root_bending_Nm` | half-wing root bending moment | N m | consistent SI arms required |
| `A_over_c` | trailing-edge camber amplitude | dimensionless | spanwise design variable |
| `twist_deg` | section twist increment | deg | spanwise design variable |
| `delta_deg` | hinged-control deflection | deg | positive sign must be stated by study |
| `CL_error` | achieved minus target lift coefficient | dimensionless | trim convergence diagnostic |
| `drag_count` | `1e-4` in drag coefficient | dimensionless shorthand | 0.115 count = 0.0000115 |

Do not use legacy fields named `morph_region_hinge_torque_proxy_Nm` or
`TE_displacement_m` without reading `AUDIT_AND_CORRECTIONS.md`. Their historical
labels were not dimensionally reliable.


