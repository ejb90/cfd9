# Haas-Sturtevant Cylindrical SBI Cases

This directory contains generators for UCNS3D case-407 inputs for the
cylindrical shock-bubble experiments in Haas & Sturtevant (1987), JFM 181,
DOI [`10.1017/S0022112087002003`](https://doi.org/10.1017/S0022112087002003).
The half-domain geometry and initial shock placement follow figure 5 of
Terashima & Tryggvason (2009), DOI
[`10.1016/j.jcp.2009.02.023`](https://doi.org/10.1016/j.jcp.2009.02.023).

Generate the cases with:

```bash
python3 cases/haas_sturtevant/generate_helium.py
python3 cases/haas_sturtevant/generate_r22.py
```

The script writes:

- `generated/helium_cylinder_ms122`
- `generated/r22_cylinder_ms122`

Each case contains `grid.msh`, `UCNS3D.DAT`, `407.nml`,
`MULTISPECIES.DAT`, `ucns3d.jcf`, a case-local `README.md`, and `case.json`.

These are upper-half-domain 2D cylindrical approximations of the 5 cm diameter
refraction-cell experiments in the 8.9 cm square test section. They do not model
the membranes, Pyrex windows, support hardware, or 3D end effects.

The default uniform meshes use 100 cells across the cylinder diameter. This
choice lies between the 80- and 160-cells-per-diameter refinement levels in
Terashima & Tryggvason section 4.1.1. Both generators document which values are
quoted from literature and which output/domain choices are derived adaptations.
