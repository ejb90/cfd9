# Convergence Case Drivers

`generate_water_air.py` creates a generated-mesh convergence set for the
cylindrical air-bubble-in-water benchmark in Terashima & Tryggvason (2009),
section 4.4, DOI [`10.1016/j.jcp.2009.02.023`](https://doi.org/10.1016/j.jcp.2009.02.023).

The mesh levels use the total-cell-doubling sequence from
`meshing/generate_mesh_suites.py`. The literature interaction geometry is:

- one bubble centred at `(0, 0, 0)` on the symmetry boundary
- bubble diameter: `0.006 m`
- initial shock-to-bubble gap: `0.0012 m`
- shock position: `x = -0.0042 m`
- final time: `4 microseconds`
- output interval: `0.05 microseconds`

The published material constants and states are:

- pre-shock water: `rho = 1000 kg/m3`, `p = 0.1 MPa`
- post-shock water: `rho = 1323.65 kg/m3`, `u = +681.58 m/s`, `p = 1 GPa`
- water EOS: `gamma = 4.4`, `p_inf = 6.0e8 Pa`
- air bubble: `rho = 1.0 kg/m3`, `gamma = 1.4`, `p = 0.1 MPa`

The geometry is reflected in x so UCNS3D profile 407 places the bubble in its
supported right ambient state; this does not change the physical problem. The
x-domain also has documented upstream/downstream padding so the established
cell-doubling suite retains approximately square cells. The bubble diameter,
shock gap, half-domain height, physical states, and interaction time are
unchanged.

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
