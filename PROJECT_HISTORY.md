# CFD9 Project History

This is a compact summary of work completed specifically for `cfd9` and its modified UCNS3D fork. It excludes everything introduced by the initial commit (`670e1c4`), which was inherited from the earlier CFD8 project.

## 1. UCNS3D problems and bugs

### Build and dependency integration

The original UCNS3D build did not reliably assemble GKlib, METIS, ParMETIS, UCNS3D, and MPI. The build scripts were reworked to:

- Clone and build the dependencies in the correct order.
- Ensure ParMETIS uses the intended METIS and GKlib builds.
- Stage headers and static libraries without requiring unreliable full installs.
- Avoid failing optional METIS executable targets.
- Keep compiler, MPI, and dependency builds consistent.
- Clone and build UCNS3D, then run a real one-timestep smoke test.
- Support clean builds in a fresh directory, including under `/tmp`.

The smoke-test path was also fixed to retain failed cases, use an absolute executable path, detect Git LFS mesh pointers, capture MPI failures, and validate genuine time advancement and output.

### Incomplete N-material Allaire implementation

The original multispecies code was only partly generalised. Although some arrays and EOS operations used `nof_species`, important paths remained hard-coded for two materials:

- The nonconservative volume-fraction source updated only one state variable.
- Boundary and outflow construction used materials 1 and 2 only.
- Several profiles initialised only two materials.
- VTU output assumed a two-material layout.
- The final dependent volume fraction was not consistently reconstructed for output.

The solver was extended across `flow_operations.f90`, `flux_p.f90`, `profile.f90`, and `io.f90` to provide a first-pass N-component implementation. A three-material bubble case was used to expose and correct cases where material 3 remained absent.

This work is functional but should not yet be treated as a formally verified general N-material Allaire solver.

### VTU/PVTU output failures

Parallel output produced malformed or truncated files, XML headers without appended binary data, temporary files, and sometimes `free(): invalid pointer` or `SIGABRT`. Output mode 5 and the handling of multiple volume fractions also needed correction.

Several revisions made VTU writing more robust, restored mode 5 as the intended VTU path, and wrote all N volume fractions, including the reconstructed final fraction. Testing was strengthened to require valid per-rank VTUs/PVTU metadata and actual time stepping.

Some invalid-free failures remained specific to the production platform. Likely factors included inconsistent compiler/MPI/dependency builds, OpenMP runtime differences, or latent parallel-I/O memory corruption; the history does not establish one definitive cause for every production failure.

### Single-rank partitioning

`mpirun -np 1` failed because partitioning and communication code assumed a distributed mesh, producing invalid zero indexing. The one-rank path in `communications.f90` and `parts.f90` was corrected so both `-np 1` and `-np 2` reached time stepping.

### MPI and platform diagnostics

Other investigated problems included:

- PRRTE's misleading `prun:exe-not-accessible` output.
- Missing MPI network interfaces inside the execution sandbox.
- ParMETIS linked against inconsistent METIS/GKlib builds.
- Git LFS mesh pointers being mistaken for real mesh files.
- Differences between local and production compiler, OpenMPI, and `libgomp` environments.

## 2. UCNS3D features added or expanded

### Configurable N-material bubble profile

Case 407 was introduced to replace hard-coded bubble definitions. Its `407.nml` namelist supports an arbitrary number of bubbles with configurable properties such as:

- Centre and size.
- Material identity.
- Density.
- Surface perturbation parameters.

Case 407 was made independent of `405.DAT`. The input roles were clarified:

- `UCNS3D.DAT` controls the solver and numerical methods.
- `407.nml` defines the initial bubble geometry and state.
- `MULTISPECIES.DAT` defines material EOS and thermodynamic properties.

### N-component state and output handling

Material-dependent operations were expanded to loop over the configured materials. Three-material initialisation was added, and VTU output now exposes all N volume fractions rather than only the `N-1` independently stored variables.

### Synthetic schlieren

A density-gradient-based synthetic schlieren quantity was added to UCNS3D and written to VTU output. A VisIt script, `analysis/schlieren_t0.visit.py`, was added to render the field with an inverted X-ray-style colour map and a view suitable for comparison with experimental images.

### More robust VTU output and single-rank execution

Although driven by bugs, the work also expanded supported workflows:

- Output mode 5 was restored as a usable VTU path.
- Parallel VTU writing was made more defensive.
- All material volume fractions were exposed for post-processing.
- Single-rank UCNS3D runs became supported without ParMETIS-style distributed partitioning assumptions.

## 3. New Python and workflow features

### Mesh generation

A FOSS Python meshing workflow replaced dependence on Pointwise:

- `meshing/make_channel_mesh.py` generates UCNS3D-compatible unstructured channel meshes with local bubble-region refinement and coarser inlet/outlet zones.
- `meshing/generate_mesh_suites.py` generates both Pointwise-like suites and systematic convergence suites using dataclass-based configurations.
- Meshes use clean `mesh_<ncells>` names, with convergence progression based on controlled cell-count and edge-length changes.
- A generated coarse mesh was smoke-tested through a UCNS3D output timestep.

### Case and convergence-study generation

The convergence setup script was improved to validate inputs, accept an explicit UCNS3D executable, derive reliable names, generate Slurm jobs, and require profile 407.

A general Python case generator, `cases/generate_cases.py`, was then developed. It can create complete UCNS3D cases with:

- Arbitrary numbers of bubbles.
- Configurable materials, density, location, and diameter.
- Density inferred from the material state when not explicitly supplied.
- Configurable domain, shock, and physical mesh spacing.
- Generated mesh, `UCNS3D.DAT`, `407.nml`, `MULTISPECIES.DAT`, scheduler files, and documentation.

Thin wrappers reproduce the Haas–Sturtevant helium and R22 cylindrical shock–bubble experiments. Their domains include additional upstream shock-development distance and downstream travel distance. A water–air convergence example was also added using material properties from the specified literature case.

### Run monitoring

`analysis/monitor_runs.py` recursively finds UCNS3D cases and reports mesh size and run state. It supports Slurm when available but also works on copied results without Slurm. Existing history, grid, and VTU output files are treated as evidence that a run started, avoiding reliance on marker files alone.

### Mesh-convergence analysis

`analysis/mesh_convergence.py` was refactored to process collections of `mesh_*` run directories, extract the required data, reproduce convergence plots, and report a converged physical mesh spacing. That spacing can then be used when generating physically different domains.

### Multi-objective optimisation

A first UCNS3D optimisation framework was added under `optimisation/`:

- Uses `pymoo`.
- Is configured by a Python driver rather than JSON.
- Allows users to select parameters and bounds.
- Creates one UCNS3D/Slurm job per population point.
- Polls jobs and consumes computed objective metrics.
- Runs under Python 3.12 through `uv`.

### Optimisation metrics

`analysis/compute_ucns3d_metrics.py` reads VTU/PVTU time series and writes optimisation-ready JSON containing:

- `Ap95_target`: robust target pressure amplification.
- `Ip_target`: normalised target pressure impulse.
- `Mbad_target`: undesirable-material contamination penalty.
- `Lp_localisation`: optional pressure-localisation ratio.

It handles configurable fields and regions, cell areas, time metadata and fallbacks, error cases, and debugging metadata. The equations and optimisation directions are documented in `analysis/compute_ucns3d_metrics.README.md`.

## Repository scope

Project-specific solver changes are in `build/UCNS3D`. The nested GKlib, METIS, and ParMETIS repositories remain upstream dependency checkouts; the project work concerning them was build and linkage integration rather than changes to their algorithms.
