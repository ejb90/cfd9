# r22_cylinder_ms122

Convergent R22-cylinder case, figure 11, Ms=1.22.

Generated from `haas_sturtevant/generate_cases.py`.

Paper setup represented here:
- 2D cylindrical case only.
- Test section height: 0.089 m.
- Cylinder diameter: 0.05 m.
- Incident shock Mach number: 1.22.
- Shock initially at x = 0.1 m, travelling right-to-left.
- Pre-shock air: rho = 1.198 kg/m3, p = 101325 Pa, u = 0 m/s.
- Post-shock air: rho = 1.648884 kg/m3, p = 159059.98 Pa, u = -114.76066 m/s.
- Shock speed magnitude: 419.68 m/s.
- Bubble/cylinder gas: r22, rho = 3.69 kg/m3, gamma = 1.17.

This is an inviscid Euler/Allaire-model approximation. It does not model the
nitrocellulose membrane, Pyrex windows, support structure, or 3D end effects.
