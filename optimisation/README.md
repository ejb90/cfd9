# UCNS3D optimisation controller

The optimisation is run by one long-lived, one-core Slurm controller job. The
controller owns the `pymoo` optimiser, generates UCNS3D cases, submits the
parallel evaluation jobs, polls Slurm, post-processes completed solutions, and
passes their objective values back to `pymoo`.

The controller job is deliberately simple. It requests one task on the
`serial` partition for 72 hours. Each evaluation is submitted with the
`ucns3d.jcf` generated in that evaluation directory; edit the shared case
generator if its parallel Slurm settings need to change.

## Study definition

Copy or edit `optimisation/example_driver.py`. The study-specific sections are:

- `PARAMETERS`: optimiser variable names and lower/upper bounds.
- `make_case(values, evaluation_index)`: converts one parameter vector into a
  `CaseConfig`, including any number of `Bubble` objects.
- `objective(run_dir, values)`: reads the completed VTU/PVTU series and returns
  the values minimised by `pymoo`.

For example, independent coordinates for two bubbles can be defined as:

```python
PARAMETERS = (
    Parameter("bubble_1_x", -0.010, 0.010),
    Parameter("bubble_1_y",  0.010, 0.040),
    Parameter("bubble_2_x",  0.015, 0.050),
    Parameter("bubble_2_y",  0.010, 0.040),
)
```

The corresponding `make_case()` uses those values when constructing its two
`Bubble` entries. Fixed properties such as material, shock Mach number, mesh
spacing, and diameter can remain ordinary Python constants. A property only
needs to appear in `PARAMETERS` when the optimiser is allowed to change it.

`pymoo` minimises every returned objective. Negate physical quantities which
should be maximised:

```python
return (
    -metrics["Ap95_target"],
    -metrics["Ip_target"],
     metrics["Mbad_target"],
)
```

The `n_obj` passed to `run_optimisation()` must equal the number of returned
values.

## Water-air single-cavity trial

`optimisation/water_air_single_bubble_driver.py` is the first production trial.
It uses one cylindrical air cavity in water with a fixed 1 GPa incident shock
and optimises two quantities:

```text
bubble_density_kg_m3:  0.5 <= density <= 2.0 kg/m3
bubble_radius_mm:     0.25 <= radius  <= 0.75 mm
```

The two objectives maximise `Ap95_target` and minimise `Mbad_target` in a fixed
circular water region 2 mm downstream of the bubble centre. The target is
separate from every permitted initial bubble, so its initial air fraction is
zero and the contamination objective remains meaningful.

The full physical rationale, bounds, target definition, literature relationship,
and limitations are documented in the driver docstring. Its default fixed mesh
spacing gives 208,000 cells. Change it with
`--cells-per-reference-diameter N`; selected Pareto candidates should later be
rerun on finer meshes.

Prepare a small inspection population:

```bash
uv run python optimisation/water_air_single_bubble_driver.py \
  --prepare-only \
  --population 4 \
  --seed 7 \
  --work-dir optimisation_runs/water_air_single_inspection
```

Launch the three-day campaign:

```bash
uv run python optimisation/water_air_single_bubble_driver.py \
  --launch-controller \
  --population 16 \
  --generations 1000 \
  --max-concurrent 4 \
  --cells-per-reference-diameter 80 \
  --poll-interval 300 \
  --seed 7 \
  --work-dir optimisation_runs/water_air_single \
  --ucns3d build/UCNS3D/src/ucns3d_p
```

## Inspect cases without Slurm

Generate the first population without submitting anything:

```bash
uv run python optimisation/example_driver.py \
  --prepare-only \
  --population 4 \
  --work-dir optimisation_runs/inspection
```

Inspect the mesh, `407.nml`, `MULTISPECIES.DAT`, `UCNS3D.DAT`, and generated JCF
before launching a real campaign. `--prepare-only` can only construct the first
generation because later populations depend on objective values from the first.

## Launch the three-day controller

From the repository root:

```bash
uv run python optimisation/example_driver.py \
  --launch-controller \
  --population 32 \
  --generations 1000 \
  --max-concurrent 16 \
  --poll-interval 300 \
  --work-dir optimisation_runs/two_bubbles \
  --ucns3d build/UCNS3D/src/ucns3d_p
```

`--launch-controller` writes
`optimisation_runs/two_bubbles/optimisation-controller.jcf` and submits it with
`sbatch`. The generated controller requests:

```text
nodes:          1
tasks:          1
CPUs per task:  1
partition:      serial
wall time:      72:00:00 (three days)
```

`--generations 1000` is intentionally larger than is likely to finish in three
days. The controller continues producing generations until either that limit is
reached or its Slurm wall time expires. `--poll-interval` is in seconds, so 300
polls every five minutes.

The launch command automatically adds `--submit` inside the controller job. To
run the controller directly rather than submitting it, replace
`--launch-controller` with `--submit`.

## Iteration lifecycle

For each generation the controller performs:

1. `algorithm.ask()` obtains a population from NSGA-II or CMOPSO.
2. One directory and one UCNS3D job are created per population member.
3. Jobs are submitted up to `--max-concurrent` at a time.
4. The controller polls `squeue`; as one job leaves the queue, another waiting
   evaluation is submitted immediately.
5. Completed output is processed into `metrics.json` and `objectives.csv`.
6. Failed post-processing receives `--failure-penalty` for every objective.
7. `algorithm.tell()` advances the optimiser.
8. Input/output tables and an optimiser checkpoint are written.

The optimiser is generational: the next population is not requested until all
members of the current population have finished or failed.

## Wall-time shutdown

The controller JCF asks Slurm to send `SIGUSR1` five minutes before its
three-day limit. On receipt, the Python controller:

- stops submitting evaluations;
- cancels evaluation job IDs that it still owns;
- leaves the optimiser checkpoint at the last fully completed generation; and
- exits normally before Slurm kills the allocation.

Thus, the optimisation and its child simulations end with the serial controller
job. The five-minute warning is independent of `--poll-interval`; the signal
interrupts the controller while it is sleeping.

## Output layout

```text
optimisation_runs/two_bubbles/
├── optimisation-controller.jcf
├── controller_job_id
├── controller-<job-id>.out
├── controller-<job-id>.err
├── optimiser-checkpoint.pkl
├── generation_0000_X.csv
├── generation_0000_F.csv
└── gen_0000/
    ├── eval_000000/
    │   ├── parameters.csv
    │   ├── slurm_job_id
    │   ├── metrics.json
    │   ├── objectives.csv
    │   └── ... UCNS3D inputs and outputs
    └── eval_000001/
```

`generation_XXXX_X.csv` contains the parameter vectors proposed by `pymoo`.
`generation_XXXX_F.csv` contains the objective vectors returned to it.

## Resume for another controller allocation

To continue from the last completed generation, repeat the launch command with
`--resume` and the same study definition, population, algorithm, objective
count, and work directory:

```bash
uv run python optimisation/example_driver.py \
  --launch-controller \
  --resume \
  --population 32 \
  --generations 2000 \
  --max-concurrent 16 \
  --poll-interval 300 \
  --work-dir optimisation_runs/two_bubbles \
  --ucns3d build/UCNS3D/src/ucns3d_p
```

Here `--generations` is the total target generation number, not the number of
additional generations. A restart after an interrupted partial generation
regenerates and resubmits that generation from the last complete checkpoint.
Do not use `--resume` after changing parameter bounds or optimiser settings;
the controller rejects incompatible checkpoints.

Check controller progress with its output file or Slurm:

```bash
squeue -j "$(cat optimisation_runs/two_bubbles/controller_job_id)"
tail -f optimisation_runs/two_bubbles/controller-*.out
```
