# CFD9 and UCNS3D Project History

This document summarises the work completed across the `cfd9` repository, the modified UCNS3D fork under `build/UCNS3D`, and the GKlib, METIS, and ParMETIS dependency repositories. It is reconstructed from the Git histories and saved Codex sessions from 20 June through 5 July 2026.

The project evolved from getting UCNS3D to build and run into a broader shock–bubble interaction workflow: a modified N-material solver, reproducible case generation and meshing, run monitoring and convergence analysis, and a first multi-objective optimisation system.

## 1. UCNS3D problems and bugs

### Build and dependency problems

The initial UCNS3D build failed because GKlib, METIS, ParMETIS, UCNS3D, and the compiler/MPI environment were not consistently assembled.

Work included:

- Cloning and building GKlib, METIS, and ParMETIS in the correct order.
- Ensuring ParMETIS used the exact METIS and GKlib builds supplied by the script.
- Avoiding optional METIS executable targets that failed under GCC 15 with warnings promoted to errors and LTO enabled.
- Staging the required headers and static archives instead of relying on problematic `make install` targets.
- Establishing that UCNS3D only needs the dependency headers and static libraries; it does not require those projects to be fully installed system-wide.
- Ensuring UCNS3D was compiled and linked with mutually compatible compiler, MPI, ParMETIS, METIS, and GKlib builds.
- Making fresh builds work outside the existing repository, including a complete build test under `/tmp`.

The resulting build automation was developed first in the outer repository and then in `build/UCNS3D/local.bash`. The outer wrapper later became `scripts/build.bash`.

### Smoke-test and MPI-launch failures

The smoke test originally suffered from several independent problems:

- It appeared after an unconditional early `exit`, so it never ran.
- It assumed UCNS3D already existed before cloning it.
- Temporary smoke directories were deleted even when a run failed.
- A `set -u` cleanup-trap bug made failure handling unreliable.
- PRRTE reported `prun:exe-not-accessible`, followed by misleading missing-help-file errors.
- MPI sometimes could not see a usable network interface inside the execution sandbox.
- The initial success check looked for the wrong output/history pattern.
- Git LFS pointer files could be copied in place of real meshes.
- Relative executable paths were unreliable for some MPI launchers.

The smoke workflow was changed to:

- Retain cases under `build/smoke/`, with a `latest` pointer.
- Launch an absolute path to `ucns3d_p`.
- Copy the `perf2` inputs into a self-contained run directory.
- Detect Git LFS mesh pointers.
- Capture MPI output and exit status.
- Validate actual solver completion or expected VTU/PVTU timestep output.
- Test a real one-timestep run, rather than merely successful linking.

### The Allaire model was only partially N-material

Inspection found that the original code had N-sized arrays and some generalised mixture-EOS loops, but it was not a proper general N-material Allaire implementation.

Important defects included:

- The nonconservative volume-fraction source was applied to only one hard-coded state index.
- Boundary/outflow construction used only materials 1 and 2.
- Profile initialisation repeatedly populated only `mp_ie(1)` and `mp_ie(2)`.
- Output logic assumed a two-material field layout.
- Only the `N-1` independent volume fractions were naturally stored, while the requested output needed all `N`, including the reconstructed final fraction.
- Three-material initialisation initially produced `volume_fraction_3` close to `1e-10` everywhere because the third bubble was not correctly represented in the profile/state construction.

This led to the first N-component generalisation in UCNS3D commit `04b2cbb`, touching:

- `src/flow_operations.f90`
- `src/flux_p.f90`
- `src/io.f90`
- `src/profile.f90`

This should still be regarded as an N-component first pass, not a formally verified, publication-grade implementation of the complete N-material Allaire model.

### Broken VTU/PVTU output

The output path was one of the largest debugging areas.

Observed failures included:

- Malformed or truncated VTU files.
- Files containing XML headers but missing appended raw binary data.
- Tiny `OUT_0.vtu` files.
- Temporary `.OUT_0.vtu.*` files left behind.
- `free(): invalid pointer` and `SIGABRT` during output.
- Behaviour that differed between the local machine and the production platform.
- Only two volume-fraction fields appearing for a three-material run.
- Incorrect handling of output mode 5.
- Parallel output being more fragile than single-process output.

Several passes were made over `io.f90`:

- `ea0fbd1`: synthetic schlieren and associated output changes.
- `5540e7e`: more robust parallel VTU writing.
- `cef12d8`: reworked output mode 5 as VTU.
- Output was amended to write all N volume fractions, reconstructing the final fraction where necessary.

The final successful test criterion was actual time advancement and valid per-rank VTUs plus a PVTU wrapper, rather than the mere existence of an output filename.

### Single-rank partitioning failure

`mpirun -np 1` originally failed during partitioning. This appeared through errors including invalid indexing around the mesh partition arrays, such as:

```text
Index '0' of dimension 1 of array 'xmpiee' below lower bound of 1
```

At first this was difficult to separate from:

- Git LFS mesh corruption.
- Mixed ParMETIS/METIS builds.
- MPI runtime inconsistency.
- The multi-rank VTU crash.

A dedicated UCNS3D change fixed the one-rank path:

- Commit `6fbc562` changed `src/communications.f90` and `src/parts.f90`.
- Single-rank execution was made to bypass or correctly handle distributed partitioning assumptions.
- Both `-np 1` and `-np 2` were explicitly tested.
- The single-rank case was confirmed to reach time stepping.

### Production-only MPI/OpenMP failures

The production platform still exposed `SIGABRT`, invalid frees, and stack traces around ParMETIS, VTU output, or `libgomp`.

The investigation established several likely contributors:

- Mixing compiler/MPI families between dependency and solver builds.
- ParMETIS linking against a different METIS/GKlib build than expected.
- Build-time and runtime OpenMPI module mismatch.
- MPI failures being obscured by missing PRRTE help files.
- OpenMP/runtime behaviour differing between the workstation and cluster.
- Parallel I/O revealing memory corruption or runtime incompatibility that did not appear locally.

The source was made more defensive, but the project history does not establish one proven root cause for every production-platform invalid-free failure.

## 2. UCNS3D features added or expanded

### Generalised N-component support

The solver was extended beyond its effectively two-material assumptions:

- Loops were introduced across material-dependent state and EOS operations.
- The Allaire nonconservative treatment was expanded across the independent volume fractions.
- Profiles and output were made aware of more than two materials.
- Three-material testing was added.
- VTU output was changed to expose all N volume fractions, including the reconstructed final material fraction.

This is best described as a functional first pass that still needs systematic numerical verification.

### Three-material bubble test

Case 405 was extended during development to include a third material and another circular bubble. This exposed the volume-fraction and output defects and became the practical test for the N-material changes.

### New configurable case 407

A new bubble-profile mode was added so simulations no longer needed bubble geometry and properties hard-coded in `profile.f90`.

The original plain-text `BUBBLE.DAT` idea evolved into a Fortran namelist named `407.nml`.

It allows an arbitrary number of bubbles, with properties including:

- Centre position.
- Radius or diameter.
- Material identity.
- Density.
- Perturbation mode and amplitude.
- Other profile controls.

Additional changes included:

- Case 407 was made independent of `405.DAT`.
- Required global and freestream inputs were moved into or represented directly by the 407 configuration where appropriate.
- The distinction between profile geometry and `MULTISPECIES.DAT` thermodynamic material definitions was clarified.

The implementation primarily affected:

- `src/parameters.f90`
- `src/profile.f90`
- `src/declarations.f90`

### Synthetic schlieren output

UCNS3D did not originally provide a synthetic schlieren field. It had Q-criterion and shock/troubled-cell sensors, but no density-gradient-based visualisation output.

A synthetic schlieren capability was added in commit `ea0fbd1`, using a density-gradient-derived quantity suitable for comparison with experimental schlieren imagery. It was written into VTU output so it could be visualised directly in ParaView or VisIt.

A companion VisIt script was added at `analysis/schlieren_t0.visit.py`, initially configured to:

- Load an `OUT*.vtu` from the working directory.
- Display the schlieren field.
- Use an inverted X-ray-style colour map.
- Apply a consistent view intended to resemble empirical schlieren images.
- Produce the initial-time image.

### Easier bubble input and documentation

The UCNS3D fork gained:

- A simpler, self-contained bubble input route.
- Better defaults and validation around case 407.
- Top-level instructions explaining the required files and how to run a case.
- Clearer separation between:
  - `UCNS3D.DAT`: solver and numerical configuration.
  - `407.nml`: geometry and initial bubble configuration.
  - `MULTISPECIES.DAT`: material EOS and thermodynamic definitions.
  - The mesh and executable.

## 3. Python features

The outer `cfd9` repository contains most of the experiment-facing work.

### Existing post-processing imported from CFD8

The initial commit brought forward a broad analysis toolkit, including:

- Interface tracking.
- Eulerian density plots.
- Enstrophy and combined-enstrophy plots.
- Mixing-mass calculations.
- Mesh-characteristic inspection.
- Mesh-convergence analysis.
- WENO comparisons.
- Temporal pseudocolour plots and montages.
- Qualitative comparisons through Python and VisIt.
- PVTU-combination workarounds.

These formed the starting point rather than all being newly written during the IRP phase.

### UCNS3D-compatible mesh generation

`meshing/make_channel_mesh.py` generates UCNS3D/Gmsh-style channel meshes with:

- Unstructured cells rather than a purely regular quad grid.
- Local refinement around the bubble and interaction region.
- Coarser inlet and outlet regions.
- Configurable domain extents and resolution.
- Boundary definitions suitable for the UCNS3D case.

`meshing/generate_mesh_suites.py` adds:

- A dataclass describing each mesh.
- Suites approximating the provided Pointwise meshes.
- A systematic convergence suite.
- Clean `mesh_<ncells>` naming.
- Resolution progression based on cell-count doubling, meaning edge length is approximately halved every second mesh.
- Standalone mesh generation separated from suite orchestration.

A coarse generated mesh was smoke-tested by running UCNS3D through one output timestep.

### Convergence-study preparation

`cases/convergence/convergence1.bash` was expanded to:

- Accept an input repository and optional `ucns3d_p` path.
- Fall back to an executable in the current directory.
- Find and stage meshes reliably.
- Validate that the selected UCNS3D profile is case 407.
- Derive cleaner directory and Slurm job names.
- Preserve useful date/time naming.
- Improve validation and error messages.
- Generate a complete directory of runnable convergence cases.

The related Python convergence analysis was substantially refactored in `analysis/mesh_convergence.py` to:

- Scan multiple run directories such as `mesh_*`.
- Extract mesh and solution information.
- Recreate the existing convergence plots.
- Reduce unnecessary mesh-reading dependencies where plain-text data already exists.
- Report a converged physical mesh spacing, which can then be supplied to later case generators even when their total domain sizes differ.

### Haas–Sturtevant case generation

A reproducible setup was built for the 1987 Haas and Sturtevant cylindrical shock–bubble experiments:

- Divergent helium case.
- Convergent R22 case.
- Enlarged upstream region to allow clean shock development.
- Enlarged downstream test region to capture bubble motion and later evolution.
- Generation of the mesh and all required UCNS3D inputs.

The first case-specific generator was later generalised into `cases/generate_cases.py`.

It supports:

- Arbitrary numbers of bubbles.
- Bubble material selection.
- Explicit density or density derived from material state using `p/(RT)`.
- Position and diameter.
- Domain and shock configuration.
- Mesh resolution specified by physical mean cell width rather than arbitrary total cell count.
- Strict floating-point configuration fields.
- Generation of `UCNS3D.DAT`, `407.nml`, `MULTISPECIES.DAT`, scheduler files, documentation, and meshes.

Thin case wrappers were then added:

- `cases/haas_sturtevant/generate_helium.py`
- `cases/haas_sturtevant/generate_r22.py`

The intention is that the generators are sufficient to regenerate the complete experiment setup, rather than relying on manually retained generated data.

### Water–air convergence example

`cases/convergence/generate_water_air.py` was added as a second physical example:

- Water background.
- Air bubble.
- Material properties based on the referenced `10.1063/1.4914133` study.
- The same systematic convergence-mesh concept used for the earlier gas-bubble cases.

This also exercised the generalised case-generation API with materially different fluids.

### Run monitoring

`analysis/monitor_runs.py` recursively discovers UCNS3D run directories and reports:

- Directory name.
- Mesh cell count.
- Whether a run has started.
- Running or queued Slurm state where available.
- Failed completion.
- Successful completion against the requested final simulation time.

It was deliberately made useful away from a cluster:

- Slurm is optional.
- Copied run directories can still be classified.
- Existing `OUT*.vtu`, history, grid, and related output artefacts count as evidence that a run started, even if no explicit `start` marker remains.

### Optimisation with pymoo and Slurm

A first multi-objective optimisation framework was added under `optimisation/`:

- Uses `pymoo`.
- Is driven by a Python script rather than JSON.
- Lets users declare parameters and bounds directly in Python.
- Creates one UCNS3D case or job for each population point.
- Supports Slurm submission and polling.
- Keeps Dask out of the initial design.
- Was verified under Python 3.12 through `uv`.

Key files are:

- `optimisation/ucns3d_pymoo.py`
- `optimisation/example_driver.py`
- `optimisation/README.md`

### Objective-metric extraction

`analysis/compute_ucns3d_metrics.py` reads UCNS3D VTU/PVTU sequences and emits optimisation-ready JSON.

It calculates:

- `Ap95_target`: maximum target-region 95th-percentile pressure, normalised by incident pressure.
- `Ip_target`: time-integrated, area-weighted target pressure excess.
- `Mbad_target`: maximum undesirable-material fraction in the target.
- `Lp_localisation`: optional fraction of excess pressure localised in the target relative to a larger interaction region.

It includes:

- VTU and PVTU discovery.
- Time extraction with fallback and warnings.
- Robust cell-area computation.
- Box and circular region selection.
- Configurable pressure and material-field names.
- Error handling for missing fields, empty regions, bad time sequences, and area failures.
- Debugging metadata in the output JSON.
- Integration with the optimisation evaluator.

The mathematics, assumptions, normalisation, and maximise/minimise directions are documented extensively in `analysis/compute_ucns3d_metrics.README.md`.

## Dependency repository status

The nested repositories are:

- `build/GKlib`
- `build/METIS`
- `build/ParMETIS`
- `build/UCNS3D`

Only UCNS3D contains project-specific solver commits. GKlib, METIS, and ParMETIS remain upstream dependency checkouts. Their relevance to this project is the build/link integration and diagnosis of ABI, compiler, and MPI consistency problems, rather than custom algorithms committed inside those repositories.

At the time this history was reconstructed, the outer `cfd9` tree was clean. The only present uncommitted change was `build/UCNS3D/local.bash`, inside the nested UCNS3D repository.
