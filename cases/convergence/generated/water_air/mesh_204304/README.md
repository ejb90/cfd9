# mesh_204304

Water-background/air-bubble convergence case. Geometry follows the original two-bubble He/Kr setup; material properties follow the air-bubble-in-water shock-collapse case.

Generated from `cases/generate_cases.py`.

Case setup:
- Domain: x=[-0.25, 0.25], y=[0, 0.1] m.
- Refined x band: [-0.15, 0.15] m.
- Requested refined-region h: 0.00044247788 m.
- Actual centre dx: 0.00044247788 m.
- Actual dy: 0.00044247788 m.
- Mesh cells: x=904, y=226, total=204304.
- Shock initially at x = -0.1 m, travelling right-to-left.
- Left ambient state: rho = 1222.8593 kg/m3, p = 1e+09 Pa, u = 434.01946 m/s.
- Right ambient state: rho = 993.89 kg/m3, p = 101325 Pa, u = 0 m/s.
- Shock speed magnitude: 2317.9735 m/s.

Materials:
- 1: water, rho = 993.89 kg/m3, gamma = 4.4, pinf = 6e+08 Pa.
- 2: air, rho = 1.204 kg/m3, gamma = 1.4, pinf = 0 Pa.

Bubbles:
- 1: material=air, center=-0.05, 0.05, 0.0 m, diameter=0.05 m, density=1.204 kg/m3.
- 2: material=air, center=0.05, 0.05, 0.0 m, diameter=0.05 m, density=1.204 kg/m3.
