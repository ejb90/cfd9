# r22_cylinder_ms122

Convergent R22-cylinder case, figure 11, Ms=1.22.

Generated from `cases/generate_cases.py`.

Case setup:
- Domain: x=[-0.175, 0.15], y=[-0.0445, 0.0445] m.
- Refined x band: [-0.05, 0.075] m.
- Requested refined-region h: 0.00016666667 m.
- Actual centre dx: 0.00016666667 m.
- Actual dy: 0.00016666667 m.
- Mesh cells: x=1950, y=534, total=1041300.
- Shock initially at x = 0.05 m, travelling right-to-left.
- Left ambient state: rho = 1.198 kg/m3, p = 101325 Pa, u = 0 m/s.
- Right ambient state: rho = 1.648884 kg/m3, p = 159059.98 Pa, u = -114.76066 m/s.
- Shock speed magnitude: 419.68 m/s.

Materials:
- 1: air, rho = 1.198 kg/m3, gamma = 1.4, pinf = 0 Pa.
- 2: r22, rho = 3.69 kg/m3, gamma = 1.2329498, pinf = 0 Pa.

Bubbles:
- 1: material=r22, center=0.0, 0.0, 0.0 m, diameter=0.05 m, density=3.69 kg/m3.
