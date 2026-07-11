# r22_cylinder_ms122

Convergent R22-cylinder case, figure 11, Ms=1.22.

Generated from `cases/generate_cases.py`.

Case setup:
- Domain: x=[-0.35, 0.25], y=[0, 0.089] m.
- Refined x band: [-0.05, 0.055] m.
- Requested refined-region h: 0.0005 m.
- Actual centre dx: 0.0005 m.
- Actual dy: 0.0005 m.
- Mesh cells: x=705, y=178, total=125490.
- Shock initially at x = 0.1 m, travelling right-to-left.
- Left ambient state: rho = 1.198 kg/m3, p = 101325 Pa, u = 0 m/s.
- Right ambient state: rho = 1.648884 kg/m3, p = 159059.98 Pa, u = -114.76066 m/s.
- Shock speed magnitude: 419.68 m/s.

Materials:
- 1: air, rho = 1.198 kg/m3, gamma = 1.4, pinf = 0 Pa.
- 2: r22, rho = 3.69 kg/m3, gamma = 1.17, pinf = 0 Pa.

Bubbles:
- 1: material=r22, center=0.0, 0.0445, 0.0 m, diameter=0.05 m, density=3.69 kg/m3.
