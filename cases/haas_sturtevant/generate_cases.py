#!/usr/bin/env python3
"""Generate UCNS3D inputs for Haas & Sturtevant cylindrical SBI cases.

This builds two 2D cylindrical approximations of:

  Haas & Sturtevant (1987), JFM 181, "Interaction of weak shock waves
  with cylindrical and spherical gas inhomogeneities"

The generated cases model the 5 cm diameter cylindrical refraction cell in the
8.9 cm square shock-tube test section. They use UCNS3D case 407 with a circular
material region and a planar incident shock.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "meshing"))

from make_channel_mesh import linspace, piecewise_x, write_mesh  # noqa: E402


@dataclass(frozen=True)
class Gas:
    name: str
    gamma: float
    density: float
    sound_speed: float


@dataclass(frozen=True)
class Experiment:
    name: str
    description: str
    bubble_gas: Gas
    mach: float
    final_time: float
    output_interval: float


@dataclass(frozen=True)
class ShockState:
    p1: float
    rho1: float
    u1: float
    p2: float
    rho2: float
    u2: float
    shock_speed: float


AIR = Gas("air", gamma=1.4, density=1.198, sound_speed=344.0)

# The paper notes strong helium contamination in the cylinder for the Ms=1.22
# case, estimating an internal sound speed of about 833 m/s rather than pure
# helium's 1010 m/s. The density below is a simple helium-air-mixture proxy.
HELIUM_MIX = Gas("helium_mixture", gamma=1.48, density=0.216, sound_speed=833.0)

# Paper value: R22 vapour density 3.69 kg/m3 and sound speed 184 m/s at
# atmospheric pressure and 25 C. gamma is chosen to remain close to that sound
# speed under the ideal/stiffened-gas p_inf=0 model used here.
R22 = Gas("r22", gamma=1.17, density=3.69, sound_speed=184.0)

AMBIENT_PRESSURE = 101_325.0
TEST_SECTION_HEIGHT = 0.089
DOMAIN_XMIN = -0.35
DOMAIN_XMAX = 0.25
CYLINDER_RADIUS = 0.025
CYLINDER_CENTER = (0.0, TEST_SECTION_HEIGHT / 2.0, 0.0)
SHOCK_POSITION_X = 0.100

EXPERIMENTS = (
    Experiment(
        name="helium_cylinder_ms122",
        description="Divergent helium-cylinder case, figure 7, Ms=1.22.",
        bubble_gas=HELIUM_MIX,
        mach=1.22,
        final_time=983.0e-6,
        output_interval=10.0e-6,
    ),
    Experiment(
        name="r22_cylinder_ms122",
        description="Convergent R22-cylinder case, figure 11, Ms=1.22.",
        bubble_gas=R22,
        mach=1.22,
        final_time=1_020.0e-6,
        output_interval=10.0e-6,
    ),
)


def normal_shock_state(mach: float, gas: Gas, pressure: float) -> ShockState:
    gamma = gas.gamma
    p_ratio = 1.0 + 2.0 * gamma / (gamma + 1.0) * (mach * mach - 1.0)
    rho_ratio = ((gamma + 1.0) * mach * mach) / ((gamma - 1.0) * mach * mach + 2.0)
    shock_speed = mach * gas.sound_speed
    particle_speed = shock_speed * (1.0 - 1.0 / rho_ratio)
    return ShockState(
        p1=pressure,
        rho1=gas.density,
        u1=0.0,
        p2=pressure * p_ratio,
        rho2=gas.density * rho_ratio,
        u2=-particle_speed,
        shock_speed=shock_speed,
    )


def write_multispecies(path: Path, bubble_gas: Gas) -> None:
    path.write_text(
        "\n".join(
            [
                "!------------MULTI-SPECIES DAT FILE-----!",
                "!--------------UCNS3D-------------------!",
                "2\t\t!NUMBER OF SPECIES",
                f"{AIR.gamma:.8g}\t{bubble_gas.gamma:.8g}\t!GAMMAS: air, {bubble_gas.name}",
                "1.0\t0.0\t!INFLOW VOLUME FRACTION",
                f"{AIR.density:.8g}\t{bubble_gas.density:.8g}\t!INFLOW DENSITIES",
                "0.0\t0.0\t!STIFFENED EOS PRESSURES",
                "",
            ]
        ),
        encoding="ascii",
    )


def write_407(path: Path, experiment: Experiment, shock: ShockState) -> None:
    gas = experiment.bubble_gas
    cx, cy, cz = CYLINDER_CENTER
    path.write_text(
        f"""&bubble_case
  shock_position_x = {SHOCK_POSITION_X:.8g}
  left_pressure = {shock.p1:.8g}
  left_velocity = {shock.u1:.8g}, 0.0, 0.0
  left_density = {shock.rho1:.8g}, {gas.density:.8g}
  left_volume_fraction = 1.0, 0.0
  right_pressure = {shock.p2:.8g}
  right_velocity = {shock.u2:.8g}, 0.0, 0.0
  right_density = {shock.rho2:.8g}, {gas.density:.8g}
  right_volume_fraction = 1.0, 0.0
  bubble_count = 1
/

&bubble
  bubble_center = {cx:.8g}, {cy:.8g}, {cz:.8g}
  bubble_initial_radius = {CYLINDER_RADIUS:.8g}
  bubble_perturbation_amplitude = 0.0
  bubble_perturbation_modes = 0
  bubble_perturbation_phase = 0.0
  bubble_pressure = {AMBIENT_PRESSURE:.8g}
  bubble_velocity = 0.0, 0.0, 0.0
  bubble_density = {shock.rho1:.8g}, {gas.density:.8g}
  bubble_volume_fraction = 0.0, 1.0
/
""",
        encoding="ascii",
    )


def ucns3d_dat(experiment: Experiment, shock: ShockState) -> str:
    return f"""====================================================================================================================================================================================================|
----------------------------------------------------------------------------------------UCNS3D PARAMETERS-------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
|2:2D, 3:3D ||\\|| I(STATISTICS 1=ENABLED, 0=DISABLED)  ||\\||    CODE CONFIGURATION (0=DEFAULT)
2                                0                                   -1
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
EQUATIONS: |1: Navier-Stokes |2: Euler | 3: Linear-sinewave | 4: Linear-step  ||\\||  Initial conditions profile (4 DEFAULT)
        -1                                      407
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
TURBULENCE MODEL ACTIVATION:1:Active 0:Deactive   ||COUPLING TURBULENCE MODEL: |1:COUPLED | 0: DECOUPLED  ||SCALAR TRANSPORT COMPUTATION (number of passive scalars [only output for the first one])
0                           0                           0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
---------------------------------------------------------------------------------------------CONDITIONS-----------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
FREE-STREAM CONDITIONS
Density ||\\|| U-velocity||\\||V-velocity ||\\||W-velocity ||\\||Pressure(if -1 then pressure=rho/gamma)
 {shock.rho2:.8g}        {shock.u2:.8g}        0.0        0.0        {shock.p2:.8g}
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
Angle of Attack ||\\|| WRT AXIS (XY-PLANE=(1 1 0),XZ-PLANE=(1 0 1))
0.0         1.0     1.0       0.0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
Gamma ||\\||Prandtl Number ||\\|| Reynolds Number ||\\||Characteristic Length
1.4       0.72         3900          0.05
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
-------------------------------------------------------------------------------------------DISCRETISATION-------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
SCHEME:1:LINEAR 2:MUSCL-TVD 3:WENO||\\||FLUX HLLC:1,RUSANOV:2,ROE:3||\\|| SPATIAL ORDER: 1-7  ||\\|| LIMITER TYPE: 1=MIN,2=BJ,3=MOGE,4=SB,5=VA,6=VL,7=VENKATA.. ||\\||POLYNOMIAL: 1: Generic  2: Legendre
3                   1              5                   1                   1
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
WENO RECONSTRUCTION: 1: CONSERVED 2: CHARACTERISTIC ||\\|| STENCILS  ||\\|| WEIGHT NORMALISATION ||\\|| WENO CENTRAL WEIGHT (lamda)
1                               5               1               10E3
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
TEMPORAL ORDER: |(1-4):RK1-RK4, 5: RK-LTS, 10: IMPLICIT BACKWARD EULER |11: IMPLICIT 2ND-ORDER ||\\|| CFL ||\\||DTS TIMESTEP SIZE ||\\|| ITERATION (FOR DTS ONLY) ||\\|| Residual THRESHOLD
4                                                  1.4       1.9          30              0.000001
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
BOUNDARY CONDITIONS: 0: Non-Periodic 1: Periodic ||\\||  BOUNDARY CONDITIONS: 0: SUPERSONIC 1: SUBSONIC  ||\\||  SCALING FACTOR:
0                           0                           1.0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
Gradients Approximation(All Least squares=0, Green Gauss=1)||\\|| LOW MACH TREATMENT (1 ACTIVATE, 0 DISABLE),
            0                       0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
-------------------------------------------------------------------------------------------I/O OPERATIONS-------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
TOTAL SIMULATION TIME SECONDS  ||\\|| TOTAL NUMBER OF ITERATIONS ||\\|| WALL CLOCK MAXIMUM TIME - REAL SECONDS:
{experiment.final_time:.8g}                 100000000          432000
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
TECPLOT:1(BIN),0(ASCII),PARAVIEW BIN:2 ||\\|| WRITE OUTPUT RATE (SEC) ||\\|| WRITE RESTART RATE(SEC) ||\\|| WRITE AVERAGE OUTPUT RATE(SEC) ||\\||PRINT THE STENCILS AT THE PROBE POSITION(0 NOW, 1 YES)
5                       {experiment.output_interval:.8g}         20000             50000                   0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
AVERAGING (0-Disabled, 1-Enabled, computing mean and RMS) Only possible for Unsteady computations ||
0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
COMPUTE FORCES: 1: ACTIVE  0: DEACTIVE ||\\|| FREQUENCY:HOW OFTEN IN ITERATIONS ||\\|| Write shear stresses 1: enable 0: disable
0                       1000                    0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
SIMULATION AVAILABLE: TURBULENT (PREVIOUS YES=1,0=NO)||\\|| TYPE (UNSTEADY YES=1,0=STEADY)||\\|| PASSIVE (PREVIOUS YES=1,0=NO) ||\\|| PREVIOUS TURBULENCE MODEL (SA=1, K-OMEGA=2)
0                               0               0                   0
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
|----------------------------------------------------------------------------------------------PROBES-----------------------------------------------------------------------------------------------|
====================================================================================================================================================================================================|
!NUMBER OF PROBES!
0               ||NUMBER OF PROBE POSITIONS. They probe density, velocities and PS
!COORDINATES
0.50001    0.50001      0.0        ||PROBE POSITION #1

"""


def write_job_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
#SBATCH --job-name=haas-sturtevant
#SBATCH --comment=UCNS3D
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --output=out
#SBATCH --error=err
#SBATCH --time=72:00:00
#SBATCH --mem-bind=local
#SBATCH --partition=parallel
#SBATCH --mem=0

set -euo pipefail

date -Iseconds > start
rm -f Errors.dat errors.dat fort* GRID* history.tct history.txt OUT*.vtu OUT*.pvtu RESTART.dat ucns3d.err ucns3d.out pos*

module purge
module load gcc/12.3.0
module load openmpi/4.1.6

time srun.awe -np "${SLURM_NTASKS:-128}" ./ucns3d_p > ucns3d.out 2> ucns3d.err
date -Iseconds > done
""",
        encoding="ascii",
    )
    path.chmod(0o755)


def write_notes(path: Path, experiment: Experiment, shock: ShockState) -> None:
    path.write_text(
        f"""# {experiment.name}

{experiment.description}

Generated from `haas_sturtevant/generate_cases.py`.

Paper setup represented here:
- 2D cylindrical case only.
- Test section height: {TEST_SECTION_HEIGHT} m.
- Cylinder diameter: {2.0 * CYLINDER_RADIUS} m.
- Incident shock Mach number: {experiment.mach}.
- Shock initially at x = {SHOCK_POSITION_X} m, travelling right-to-left.
- Pre-shock air: rho = {shock.rho1:.8g} kg/m3, p = {shock.p1:.8g} Pa, u = 0 m/s.
- Post-shock air: rho = {shock.rho2:.8g} kg/m3, p = {shock.p2:.8g} Pa, u = {shock.u2:.8g} m/s.
- Shock speed magnitude: {shock.shock_speed:.8g} m/s.
- Bubble/cylinder gas: {experiment.bubble_gas.name}, rho = {experiment.bubble_gas.density:.8g} kg/m3, gamma = {experiment.bubble_gas.gamma:.8g}.

This is an inviscid Euler/Allaire-model approximation. It does not model the
nitrocellulose membrane, Pyrex windows, support structure, or 3D end effects.
""",
        encoding="ascii",
    )


def write_mesh_for_case(path: Path, nx: int, ny: int) -> None:
    x_left_cells = max(8, round(nx * (0.0 - DOMAIN_XMIN) / (DOMAIN_XMAX - DOMAIN_XMIN)))
    x_center_cells = max(24, round(nx * 0.105 / (DOMAIN_XMAX - DOMAIN_XMIN)))
    x_right_cells = nx - x_left_cells - x_center_cells
    if x_right_cells < 8:
        raise ValueError("nx is too small for the requested domain decomposition")
    xs = piecewise_x(
        DOMAIN_XMIN,
        DOMAIN_XMAX,
        -0.050,
        0.055,
        nx,
        x_left_cells,
        x_center_cells,
        x_right_cells,
    )
    ys = linspace(0.0, TEST_SECTION_HEIGHT, ny)
    write_mesh(path, xs, ys)


def generate_case(root: Path, experiment: Experiment, nx: int, ny: int) -> Path:
    case_dir = root / experiment.name
    case_dir.mkdir(parents=True, exist_ok=True)
    shock = normal_shock_state(experiment.mach, AIR, AMBIENT_PRESSURE)

    write_mesh_for_case(case_dir / "grid.msh", nx, ny)
    write_multispecies(case_dir / "MULTISPECIES.DAT", experiment.bubble_gas)
    write_407(case_dir / "407.nml", experiment, shock)
    (case_dir / "UCNS3D.DAT").write_text(ucns3d_dat(experiment, shock), encoding="ascii")
    write_job_script(case_dir / "ucns3d.jcf")
    write_notes(case_dir / "README.md", experiment, shock)

    return case_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "generated")
    parser.add_argument("--nx", type=int, default=480)
    parser.add_argument("--ny", type=int, default=180)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for experiment in EXPERIMENTS:
        case_dir = generate_case(args.output_dir, experiment, args.nx, args.ny)
        print(case_dir)


if __name__ == "__main__":
    main()
