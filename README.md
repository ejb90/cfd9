# cfd9
IRP

# UCNS3D

## Building

### Local Build

```
bash local.bash
```

## #Docker Build

N/A

## Running

```
cp build/UCNS3D/src/ucns3d_p .
cp path/to/inputs/{grid.msh,MULTISPECIES.DAT,UCNS3D.DAT} .
mpirun ./ucns3d_p
```

### Case 407: configurable multi-material bubbles

Case `407` is the configurable Allaire multi-material bubble case. It does
not require `405.DAT` or `BUBBLE.DAT`.

Required files in the run directory:

- `ucns3d_p`
- `grid.msh`
- `UCNS3D.DAT`, with the initial condition set to `407`
- `MULTISPECIES.DAT`, with the same number of species used by `407.nml`
- `407.nml`

Run it from the directory containing those files:

```bash
mpirun --oversubscribe -np 4 ./ucns3d_p
```

`407.nml` uses one `&bubble_case` block for the shock/ambient states and one
`&bubble` block per bubble. `bubble_count` must match the number of `&bubble`
blocks. Density and volume-fraction arrays must have one entry per species,
and each volume-fraction array must sum to `1`.

Example three-material input:

```fortran
&bubble_case
  shock_position_x = -0.1
  left_pressure = 150000.0
  left_velocity = 114.49, 0.0, 0.0
  left_density = 0.166315789, 1.658, 1.431
  left_volume_fraction = 0.0, 1.0, 0.0
  right_pressure = 101325.0
  right_velocity = 0.0, 0.0, 0.0
  right_density = 0.166315789, 1.204, 1.431
  right_volume_fraction = 0.0, 1.0, 0.0
  bubble_count = 2
/

&bubble
  bubble_center = -0.05, 0.05, 0.0
  bubble_initial_radius = 0.025
  bubble_perturbation_amplitude = 0.0
  bubble_perturbation_modes = 0
  bubble_perturbation_phase = 0.0
  bubble_pressure = 101325.0
  bubble_velocity = 0.0, 0.0, 0.0
  bubble_density = 0.166315789, 1.204, 1.431
  bubble_volume_fraction = 0.95, 0.05, 0.0
/

&bubble
  bubble_center = 0.05, 0.05, 0.0
  bubble_initial_radius = 0.025
  bubble_perturbation_amplitude = 0.0
  bubble_perturbation_modes = 0
  bubble_perturbation_phase = 0.0
  bubble_pressure = 101325.0
  bubble_velocity = 0.0, 0.0, 0.0
  bubble_density = 0.166315789, 1.204, 1.431
  bubble_volume_fraction = 0.0, 0.05, 0.95
/
```
