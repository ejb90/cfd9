# Single-VTU VisIt plot tiles

`render_vtu_plots.py` renders self-describing PNG plots from one UCNS3D VTU
file. The default output set is:

- density;
- numerical schlieren;
- pressure;
- signed spanwise vorticity;
- normalised multi-material mixedness.

Each image uses the same physical view and pixel dimensions. A colour legend
is embedded by default. Axes, database names, time labels, and interpolated
interface contours are omitted so the images can later be tiled without
case-specific decorations.
The default image height is derived from the physical view, so the complete
domain is not distorted or surrounded by unused canvas space. Set both
`--width` and `--height` when a later layout requires fixed raster dimensions.

## Basic usage

```bash
python analysis/render_vtu_plots.py \
  /path/to/OUT_400.vtu \
  /path/to/plot_tiles
```

This produces `OUT_400_density.png`, `OUT_400_schlieren.png`,
`OUT_400_pressure.png`, `OUT_400_vorticity.png`,
`OUT_400_mixedness.png`, and `OUT_400_plots.json`.

## Legends

Legend output is explicit:

- `--legend-mode embedded` places the quantity, units, colour scale, and tick
  values in every plot; this is the default;
- `--legend-mode separate` keeps plots clean and writes a corresponding
  `*_legend.png` for every quantity;
- `--legend-mode none` suppresses legends entirely.

For example:

```bash
python analysis/render_vtu_plots.py OUT_400.vtu tiles \
  --legend-mode separate
```

Separate legends are extracted from VisIt's own colour bar, so their colours
and numerical ticks match the rendered plot. This mode uses ImageMagick;
override its location with `--magick /path/to/magick` if necessary.

The JSON manifest records the input, bounds, image size, volume-fraction
fields, interface selection, raw data ranges, colour limits, colour tables,
output index, embedded physical `TimeValue`, and output filenames. A later
montage script can therefore label a tile with its case specification and time
without extracting metadata from the image.

Point the launcher at a different VisIt installation with:

```bash
python analysis/render_vtu_plots.py OUT_400.vtu tiles \
  --visit /opt/visit/3.4.2/bin/visit
```

## Reproducible comparisons

Use identical bounds, dimensions, and colour limits for every member of a
comparison:

```bash
python analysis/render_vtu_plots.py OUT_400.vtu tiles/case_a \
  --bounds -0.02 0.08 0.0 0.10 \
  --width 1600 --height 900 \
  --limits density 0.1 4.6 \
  --limits pressure 1.0e5 2.0e5
```

The same command structure can be called once per bubble arrangement, mesh,
or output time. Give each invocation a unique `--prefix` when several VTUs
write to one directory.

## Materials and interfaces

Interface contours are optional because VisIt interpolates the cell-centred
volume fraction when drawing them; on a coarse mesh the resulting line can
look smoother than the underlying solution. Enable them with `--interfaces`.
Component 1 is then treated as ambient and every other numbered
`volume_fractionN` field receives a contour. Override that choice for a
multi-material case with:

```bash
python analysis/render_vtu_plots.py OUT_400.vtu tiles \
  --interfaces \
  --ambient-component 2 \
  --interface-components 1 3 4
```

Change the optional contour with `--interface-cutoff F`.

## Plot definitions

- Density and pressure use the native VTU fields.
- Schlieren uses the native `schlieren` field when present and otherwise
  evaluates `magnitude(gradient(<density>))` in VisIt. If the native field has
  a non-finite range, the renderer automatically retries with that density-gradient
  expression.
- Vorticity evaluates `curl({<u>,<v>,0*<u>})`; for a 2D mesh VisIt returns the
  signed out-of-plane component.
- For `N` material volume fractions, mixedness is
  `N/(N-1) * (1-sum(alpha_i^2))`. Its plotting range is fixed to `[0,1]`.

Render only a subset with, for example, `--plots density pressure`. Existing
outputs are protected unless `--overwrite` is supplied.

## Time series

`render_vtu_time_series.py` applies the same rendering options to selected
VTUs and writes all tiles into one flat directory. Select frames in one of
three mutually exclusive ways.

Explicit files, resolved relative to the run directory:

```bash
python analysis/render_vtu_time_series.py RUN_DIR tiles \
  --files OUT_0.vtu OUT_241.vtu OUT_481.vtu
```

Nearest embedded physical times, in seconds:

```bash
python analysis/render_vtu_time_series.py RUN_DIR tiles \
  --times 0 5.0e-7 1.0e-6 \
  --max-time-error 2.6e-8
```

Exact integer suffixes from `OUT_<N>.vtu` filenames:

```bash
python analysis/render_vtu_time_series.py RUN_DIR tiles \
  --timesteps 0 241 481
```

All single-VTU options are available, including `--plots`, `--bounds`,
`--width`, `--height`, `--limits`, `--interfaces`, `--interface-cutoff`,
`--interface-components`, `--ambient-component`, `--prefix`, `--overwrite`,
`--legend-mode`, `--visit`, and `--magick`. Use `--dry-run` to inspect
file/time matching without starting VisIt.

The wrapper renders a VTU only once if several requested times select the same
file. Its `time_series.json` manifest preserves every request in order and
records the chosen file, embedded physical time, error from the requested
time, output index, child manifest, and plot filenames. For meaningful visual
comparisons, supply common `--limits` for each scalar rather than allowing
every frame to autoscale independently.

Time-series plots embed legends by default, ensuring every independently
scaled tile remains interpretable. To produce one shared legend image per
quantity instead, select `--legend-mode separate` and provide fixed
`--limits` for every requested data-dependent plot. Mixedness already has the
fixed range `[0,1]`:

```bash
python analysis/render_vtu_time_series.py RUN_DIR tiles \
  --times 0 5.0e-7 1.0e-6 \
  --plots density pressure mixedness \
  --legend-mode separate \
  --limits density 0.1 4.6 \
  --limits pressure 1.0e5 2.0e5
```

The shared images are named `density_legend.png`, `pressure_legend.png`, and
so on, and are also listed in the `legends` object in `time_series.json`.
