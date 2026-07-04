# Convergence Case Drivers

`generate_water_air.py` creates a simple generated-mesh convergence set for a
two-air-bubble case in a stiffened-water background.

The mesh levels use the total-cell-doubling sequence from
`meshing/generate_mesh_suites.py`. The bubble geometry follows the original
two-bubble He/Kr setup:

- centres: `(-0.05, 0.05, 0.0)` and `(0.05, 0.05, 0.0)`
- radius: `0.025 m`
- shock position: `x = -0.1 m`
- final time/output interval match the original convergence input

The material constants are:

- water: `rho = 993.89 kg/m3`, `gamma = 4.4`, `p_inf = 6.0e8 Pa`
- air: `rho = 1.204 kg/m3`, `gamma = 1.4`, `p_inf = 0 Pa`

Generate all levels:

```bash
python3 cases/convergence/generate_water_air.py
```

Generate only the first two levels and symlink an executable:

```bash
python3 cases/convergence/generate_water_air.py \
  --limit 2 \
  --ucns3d ../build/UCNS3D/src/ucns3d_p
```
