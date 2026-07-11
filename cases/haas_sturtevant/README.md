# Haas-Sturtevant Cylindrical SBI Cases

This directory contains a generator for approximate UCNS3D case-407 inputs for
the cylindrical shock-bubble experiments in Haas & Sturtevant (1987), JFM 181.

Generate the cases with:

```bash
python3 haas_sturtevant/generate_cases.py
```

The script writes:

- `generated/helium_cylinder_ms122`
- `generated/r22_cylinder_ms122`

Each case contains `grid.msh`, `UCNS3D.DAT`, `407.nml`,
`MULTISPECIES.DAT`, `ucns3d.jcf`, a case-local `README.md`, and `case.json`.

These are 2D cylindrical approximations of the 5 cm diameter refraction-cell
experiments in the 8.9 cm square test section. They do not model the membranes,
Pyrex windows, support hardware, or 3D end effects.

The default meshes use 100 cells across the cylinder diameter, which produces
`705 x 178` cells (`125,490` total) with `dx = dy = 0.0005 m` in the refined
region.
