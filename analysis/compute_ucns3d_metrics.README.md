# UCNS3D Optimisation Metrics

`compute_ucns3d_metrics.py` post-processes UCNS3D `.vtu` or `.pvtu` outputs and
writes a compact JSON file of scalar objective metrics. The metrics are designed
for shock-bubble optimisation where the aim is strong, repeatable pressure
amplification in a desired target region while penalising contaminated or poorly
focused compression.

The script is deliberately not a visualisation tool. It reduces a full time
series of cell-centred fields to a small set of robust scalar quantities that can
be consumed by `pymoo`, Slurm campaign scripts, or another optimiser.

## Inputs

The script expects a directory containing UCNS3D output files:

- `.pvtu` files are preferred if present.
- If no `.pvtu` files are present, `.vtu` files are used.
- Files are sorted by integer groups in their filenames, then by name.

Example:

```bash
uv run python analysis/compute_ucns3d_metrics.py \
  --output-dir ./run_001 \
  --json-out ./run_001/metrics.json \
  --pressure-field pressure \
  --bad-material-field volume_fraction \
  --p-incident 1.0e9 \
  --p0 101325.0 \
  --t-ref 1.0e-6 \
  --target-box 0.045 0.065 0.040 0.060 \
  --interaction-box -0.10 0.12 0.0 0.10
```

The same functionality can be used from Python:

```python
from analysis.compute_ucns3d_metrics import write_metrics_json

metrics = write_metrics_json({
    "output_dir": run_dir,
    "json_out": run_dir / "metrics.json",
    "pressure_field": "pressure",
    "bad_material_field": "volume_fraction",
    "p_incident": 1.0e9,
    "p0": 101325.0,
    "t_ref": 1.0e-6,
    "target_region": {
        "type": "circle",
        "xc": 0.05,
        "yc": 0.05,
        "radius": 0.01,
    },
    "interaction_region": {
        "type": "box",
        "xmin": -0.10,
        "xmax": 0.12,
        "ymin": 0.00,
        "ymax": 0.10,
    },
})
```

## Fields

The script reads cell-centred data.

Required fields:

- pressure field, default `pressure`
- bad-material volume-fraction field, default `volume_fraction`

The bad-material field is configurable because UCNS3D outputs may call this
quantity `volume_fraction`, `alpha_shell`, `vf_shell`, `volfrac 3`, or another
case-specific name. The field should be a scalar cell-data array where larger
values mean more unwanted material in the target region.

Cell areas are obtained in this order:

1. A user-specified `--area-field`.
2. Existing cell-data fields named `area`, `cell_area`, or `Area`.
3. PyVista cell-size calculation:

   ```python
   mesh.compute_cell_sizes(length=False, area=True, volume=False)
   ```

For the 2D UCNS3D meshes used here, this gives the cell areas needed for
area-weighted means and pressure-excess integrals.

## Regions

Metrics are evaluated inside a fixed target region. This is the desired focus or
compression region.

Two target-region forms are supported:

```bash
--target-box xmin xmax ymin ymax
```

or:

```bash
--target-circle xc yc radius
```

The optional interaction region is a larger region around the bubble array used
for localisation:

```bash
--interaction-box xmin xmax ymin ymax
```

or:

```bash
--interaction-circle xc yc radius
```

Cells are selected by their cell-centre coordinates. A cell belongs to a region
if its centre lies inside the box or circle.

## Time Handling

For each output file, the script attempts to read simulation time from field
data. It checks these names:

- `TimeValue`
- `TIME`
- `Time`
- `time`

If no time metadata exists, it falls back to the file order:

```text
t = 0, 1, 2, ...
```

The fallback is recorded as a warning in the output JSON. This fallback is useful
for smoke tests, but physical impulse values require real simulation times.

Histories are sorted by time before integration. Non-monotonic or duplicate
times are reported in the JSON warnings.

## Metric 1: `Ap95_target`

`Ap95_target` measures robust pressure amplification inside the target region.
It is the maximum over time of the 95th percentile target pressure, normalised
by the incident shock pressure:

```text
Ap95_target = max_t(P95(p_target(t))) / p_incident
```

where:

- `p_target(t)` is the cell-centred pressure array restricted to target cells.
- `P95(...)` is the 95th percentile.
- `p_incident` is the incident shock pressure scale supplied by the user.

The 95th percentile is used instead of a raw maximum because the raw maximum can
be dominated by a single-cell numerical spike. `Ap95_target` still rewards strong
local compression, but it is less sensitive to isolated outliers.

Optimisation direction:

```text
maximise Ap95_target
```

In `pymoo`, which minimises by default, use:

```python
-metrics["Ap95_target"]
```

## Metric 2: `Ip_target`

`Ip_target` measures pressure impulse delivered to the target region. At each
output time, the script computes the area-weighted mean pressure in the target
region:

```text
mean_p_target(t) = sum_i(p_i(t) A_i) / sum_i(A_i)
```

It then integrates the positive excess above the initial/background pressure:

```text
p_excess_target(t) = max(mean_p_target(t) - p0, 0)
```

```text
Ip_target_raw = integral p_excess_target(t) dt
```

and normalises by `p_incident * t_ref`:

```text
Ip_target = Ip_target_raw / (p_incident * t_ref)
```

The time integral is evaluated with trapezoidal integration over the output
times:

```python
np.trapezoid(p_excess_history, times)
```

If only one timestep is present, the impulse is set to `0.0` and a warning is
written. A single output has no time interval over which to integrate.

Optimisation direction:

```text
maximise Ip_target
```

In `pymoo`, use:

```python
-metrics["Ip_target"]
```

## Metric 3: `Mbad_target`

`Mbad_target` penalises contamination of the target region by an unwanted
material. At each output time, the script computes the area-weighted mean of the
configured bad-material field inside the target:

```text
Mbad(t) = sum_i(alpha_bad_i(t) A_i) / sum_i(A_i)
```

The reported metric is the maximum over time:

```text
Mbad_target = max_t(Mbad(t))
```

This is a clean-compression penalty. It is high when the target region contains
the material that should not be there.

Examples of bad-material fields:

- shell/bubble contaminant volume fraction
- unwanted gas volume fraction
- a material indicator field exported by UCNS3D

Optimisation direction:

```text
minimise Mbad_target
```

In `pymoo`, use it directly:

```python
metrics["Mbad_target"]
```

## Optional Metric 4: `Lp_localisation`

`Lp_localisation` measures how concentrated the useful pressure excess is inside
the target relative to a larger interaction region.

At each output time, the script computes positive pressure-excess area
integrals:

```text
target_excess(t) =
  sum_i(max(p_i(t) - p0, 0) A_i), for i in target cells
```

```text
interaction_excess(t) =
  sum_i(max(p_i(t) - p0, 0) A_i), for i in interaction cells
```

Then:

```text
Lp_localisation = max_t(target_excess(t) / interaction_excess(t))
```

Only times with positive interaction excess are used. If no interaction region
is supplied, `Lp_localisation` is written as `null`.

This metric is useful when high target pressure is only desirable if the energy
is concentrated in the target rather than spread across the entire interaction
domain.

Optimisation direction:

```text
maximise Lp_localisation
```

In `pymoo`, use:

```python
-metrics["Lp_localisation"]
```

If `Lp_localisation` is `None`, either omit it from the objective vector or
replace it with a penalty appropriate for the study.

## Output JSON

The output JSON contains the objective metrics plus metadata useful for
debugging optimisation runs.

Typical shape:

```json
{
  "Ap95_target": 2.975,
  "Ap95_target_time": 1.0,
  "Ip_target": 1.625,
  "Ip_target_raw": 3.25,
  "Lp_localisation": 0.9,
  "Mbad_target": 0.6,
  "Mbad_target_time": 1.0,
  "bad_material_field": "volume_fraction",
  "interaction_n_cells": 4,
  "n_files": 2,
  "p0": 1.0,
  "p_incident": 2.0,
  "pressure_field": "pressure",
  "t_ref": 1.0,
  "target_n_cells": 2,
  "time_end": 1.0,
  "time_start": 0.0,
  "warnings": []
}
```

The `_time` fields report when the corresponding maximum occurred.

`Ip_target_raw` is included because it is often easier to inspect in dimensional
units before the optimisation normalisation is applied.

## Use With Optimisation

The example optimisation driver calls:

```python
from analysis.compute_ucns3d_metrics import write_metrics_json
```

and returns minimisation objectives:

```python
metrics = write_metrics_json(config)

return (
    -metrics["Ap95_target"],
    -metrics["Ip_target"],
    metrics["Mbad_target"],
)
```

This means each completed run directory contains:

- `metrics.json`: physical/post-processed metrics
- `objectives.csv`: values actually passed to `pymoo`

The sign convention is important. `metrics.json` stores human-readable physical
metrics where larger amplification/impulse is better. `objectives.csv` stores the
minimisation form required by `pymoo`.

## Failure Modes

The script fails with a clear error for:

- no `.vtu` or `.pvtu` files found
- missing pressure field
- missing bad-material field
- non-scalar requested fields
- empty target region
- invalid box/circle region
- invalid or zero cell areas
- non-positive `p_incident`
- non-positive `t_ref`

Warnings are embedded in the JSON for recoverable issues:

- missing time metadata with fallback to file order
- only one timestep, causing impulse to be set to zero
- non-monotonic or duplicate times
- interaction region supplied but no positive interaction excess found

## Notes

- The metrics use cell centres for region membership. Boundary-cut cells are not
  fractionally clipped by the region boundary.
- The metrics use cell areas, not cell counts, so they are more robust across
  non-uniform unstructured meshes.
- The script assumes pressure and material fields are cell-centred. Point-data
  fields are not interpolated.
- The 95th percentile pressure metric is intentionally robust; raw maximum
  pressure is usually too sensitive for optimisation.
