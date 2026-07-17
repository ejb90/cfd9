# mesh_1638400

Terashima--Tryggvason (2009), section 4.4, cylindrical air-bubble-in-water shock-collapse convergence case.

Generated from `cases/generate_cases.py`.

Case setup:
- Domain: x=[-0.015, 0.009], y=[0, 0.006] m.
- Refined x band: [-0.012, 0.006] m.
- Requested refined-region h: 9.375e-06 m.
- Actual centre dx: 9.375e-06 m.
- Actual dy: 9.375e-06 m.
- Mesh cells: x=2560, y=640, total=1638400.
- Shock initially at x = 0.0042 m, travelling right-to-left.
- Left ambient state: rho = 1000 kg/m3, p = 100000 Pa, u = 0 m/s.
- Right ambient state: rho = 1323.65 kg/m3, p = 1e+09 Pa, u = -681.58 m/s.
- Shock speed magnitude: 2787.4969 m/s.

Materials:
- 1: water, rho = 1000 kg/m3, gamma = 4.4, pinf = 6e+08 Pa.
- 2: air, rho = 1 kg/m3, gamma = 1.4, pinf = 0 Pa.

Bubbles:
- 1: material=air, center=0.0, 0.0, 0.0 m, diameter=0.006 m, density=1 kg/m3.
