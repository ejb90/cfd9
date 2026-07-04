# UCNS3D Optimisation

This directory contains a minimal `pymoo` + Slurm bridge for UCNS3D studies.
The intended user interface is a Python driver, not a JSON/YAML config.

Edit `example_driver.py` to define:

- `PARAMETERS`: names and bounds for optimiser variables.
- `make_case(values, evaluation_index)`: maps one optimiser point to a `CaseConfig`.
- `objective(run_dir, values)`: parses completed UCNS3D output and returns objective values.

Prepare a generation without submitting jobs:

```bash
uv run python optimisation/example_driver.py \
  --prepare-only \
  --population 4 \
  --generations 1 \
  --work-dir optimisation_runs/test
```

Submit each point as a separate Slurm job and wait for the generation:

```bash
uv run python optimisation/example_driver.py \
  --submit \
  --population 8 \
  --generations 5 \
  --work-dir optimisation_runs/helium_test \
  --ucns3d ../build/UCNS3D/src/ucns3d_p \
  --command "srun -n 2 ./ucns3d_p" \
  --max-concurrent 16
```

The example objective reads two values from `objective.txt` in each run
directory. Replace that function with the actual post-processing metric before
using `--submit` for real optimisation.
