#!/usr/bin/env python3
"""Generate UCNS3D case-407 shock/bubble inputs.

This module is deliberately case-agnostic: callers provide the domain, mesh
resolution, ambient/shock state, materials, and an arbitrary list of bubbles.
Thin wrapper scripts can then encode named experiments without duplicating the
UCNS3D.DAT, 407.nml, MULTISPECIES.DAT, mesh, and job-script writers.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "meshing"))

from make_channel_mesh import linspace, piecewise_x, write_mesh  # noqa: E402


@dataclass(frozen=True)
class Material:
    name: str
    gamma: float
    density: float
    sound_speed: float | None = None
    pinf: float = 0.0


@dataclass(frozen=True)
class ShockState:
    p1: float
    rho1: float
    u1: float
    p2: float
    rho2: float
    u2: float
    shock_speed: float


@dataclass(frozen=True)
class Bubble:
    material: Material
    center: tuple[float, float, float]
    diameter: float
    density: float | None = None
    pressure: float | None = None
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    perturbation_amplitude: float = 0.0
    perturbation_modes: int = 0
    perturbation_phase: float = 0.0

    @property
    def radius(self) -> float:
        return 0.5 * self.diameter

    @property
    def effective_density(self) -> float:
        return self.material.density if self.density is None else self.density


@dataclass(frozen=True)
class Domain:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    refined_xmin: float
    refined_xmax: float

    @property
    def height(self) -> float:
        return self.ymax - self.ymin


@dataclass(frozen=True)
class MeshResolution:
    requested_h: float
    buffer_factor: float
    y_cells: int
    x_left_cells: int
    x_center_cells: int
    x_right_cells: int

    @property
    def x_cells(self) -> int:
        return self.x_left_cells + self.x_center_cells + self.x_right_cells

    @property
    def cell_count(self) -> int:
        return self.x_cells * self.y_cells


@dataclass(frozen=True)
class CaseConfig:
    name: str
    description: str
    ambient_material: Material
    shock: ShockState
    domain: Domain
    mesh: MeshResolution
    shock_position_x: float
    final_time: float
    output_interval: float
    bubbles: tuple[Bubble, ...]
    characteristic_length: float
    reynolds_number: float = 3900.0
    cfl: float = 1.4
    dt: float = 1.9
    max_iterations: int = 100000000
    wall_clock_limit: int = 432000
    job_name: str | None = None


def normal_shock_state(mach: float, material: Material, pressure: float) -> ShockState:
    if material.sound_speed is None:
        raise ValueError(f"sound_speed is required for shock calculation: {material.name}")
    gamma = material.gamma
    p_ratio = 1.0 + 2.0 * gamma / (gamma + 1.0) * (mach * mach - 1.0)
    rho_ratio = ((gamma + 1.0) * mach * mach) / ((gamma - 1.0) * mach * mach + 2.0)
    shock_speed = mach * material.sound_speed
    particle_speed = shock_speed * (1.0 - 1.0 / rho_ratio)
    return ShockState(
        p1=pressure,
        rho1=material.density,
        u1=0.0,
        p2=pressure * p_ratio,
        rho2=material.density * rho_ratio,
        u2=-particle_speed,
        shock_speed=shock_speed,
    )


def material_list(config: CaseConfig) -> tuple[Material, ...]:
    materials = [config.ambient_material]
    seen = {config.ambient_material.name}
    for bubble in config.bubbles:
        if bubble.material.name in seen:
            continue
        materials.append(bubble.material)
        seen.add(bubble.material.name)
    return tuple(materials)


def material_index(materials: tuple[Material, ...], material: Material) -> int:
    for i, candidate in enumerate(materials):
        if candidate.name == material.name:
            return i
    raise ValueError(f"material is not in case material list: {material.name}")


def one_hot(count: int, hot_index: int) -> list[float]:
    return [1.0 if i == hot_index else 0.0 for i in range(count)]


def fmt_float(value: float) -> str:
    text = f"{value:.8g}"
    if "." not in text and "e" not in text.lower():
        text += ".0"
    return text


def fmt_int(value: int) -> str:
    return str(value)


def fmt_vector(values: list[float] | tuple[float, ...]) -> str:
    return ", ".join(fmt_float(value) for value in values)


def mesh_resolution_from_h(domain: Domain, h: float, buffer_factor: float) -> MeshResolution:
    if h <= 0.0:
        raise ValueError("h must be positive")
    if buffer_factor < 1.0:
        raise ValueError("buffer_factor must be >= 1")
    if not (domain.xmin < domain.refined_xmin < domain.refined_xmax < domain.xmax):
        raise ValueError("expected xmin < refined_xmin < refined_xmax < xmax")
    if domain.height <= 0.0:
        raise ValueError("domain ymax must be greater than ymin")

    buffer_h = h * buffer_factor
    return MeshResolution(
        requested_h=h,
        buffer_factor=buffer_factor,
        y_cells=max(1, round(domain.height / h)),
        x_left_cells=max(1, round((domain.refined_xmin - domain.xmin) / buffer_h)),
        x_center_cells=max(1, round((domain.refined_xmax - domain.refined_xmin) / h)),
        x_right_cells=max(1, round((domain.xmax - domain.refined_xmax) / buffer_h)),
    )


def write_multispecies(path: Path, config: CaseConfig) -> None:
    materials = material_list(config)
    inflow_volfrac = one_hot(len(materials), 0)
    path.write_text(
        "\n".join(
            [
                "!------------MULTI-SPECIES DAT FILE-----!",
                "!--------------UCNS3D-------------------!",
                f"{len(materials)}\t\t!NUMBER OF SPECIES",
                f"{fmt_vector(tuple(material.gamma for material in materials))}\t!GAMMAS: "
                + ", ".join(material.name for material in materials),
                f"{fmt_vector(inflow_volfrac)}\t!INFLOW VOLUME FRACTION",
                f"{fmt_vector(tuple(material.density for material in materials))}\t!INFLOW DENSITIES",
                f"{fmt_vector(tuple(material.pinf for material in materials))}\t!STIFFENED EOS PRESSURES",
                "",
            ]
        ),
        encoding="ascii",
    )


def write_407(path: Path, config: CaseConfig) -> None:
    materials = material_list(config)
    shock = config.shock
    base_densities = [shock.rho1] + [material.density for material in materials[1:]]
    shocked_densities = [shock.rho2] + [material.density for material in materials[1:]]
    ambient_volfrac = one_hot(len(materials), 0)

    blocks = [
        "&bubble_case",
        f"  shock_position_x = {fmt_float(config.shock_position_x)}",
        f"  left_pressure = {fmt_float(shock.p1)}",
        f"  left_velocity = {fmt_float(shock.u1)}, 0.0, 0.0",
        f"  left_density = {fmt_vector(base_densities)}",
        f"  left_volume_fraction = {fmt_vector(ambient_volfrac)}",
        f"  right_pressure = {fmt_float(shock.p2)}",
        f"  right_velocity = {fmt_float(shock.u2)}, 0.0, 0.0",
        f"  right_density = {fmt_vector(shocked_densities)}",
        f"  right_volume_fraction = {fmt_vector(ambient_volfrac)}",
        f"  bubble_count = {fmt_int(len(config.bubbles))}",
        "/",
        "",
    ]

    for bubble in config.bubbles:
        hot_index = material_index(materials, bubble.material)
        bubble_densities = list(base_densities)
        bubble_densities[hot_index] = bubble.effective_density
        bubble_volfrac = one_hot(len(materials), hot_index)
        pressure = shock.p1 if bubble.pressure is None else bubble.pressure
        blocks.extend(
            [
                "&bubble",
                f"  bubble_center = {fmt_vector(bubble.center)}",
                f"  bubble_initial_radius = {fmt_float(bubble.radius)}",
                f"  bubble_perturbation_amplitude = {fmt_float(bubble.perturbation_amplitude)}",
                f"  bubble_perturbation_modes = {fmt_int(bubble.perturbation_modes)}",
                f"  bubble_perturbation_phase = {fmt_float(bubble.perturbation_phase)}",
                f"  bubble_pressure = {fmt_float(pressure)}",
                f"  bubble_velocity = {fmt_vector(bubble.velocity)}",
                f"  bubble_density = {fmt_vector(bubble_densities)}",
                f"  bubble_volume_fraction = {fmt_vector(bubble_volfrac)}",
                "/",
                "",
            ]
        )

    path.write_text("\n".join(blocks), encoding="ascii")


def ucns3d_dat(config: CaseConfig) -> str:
    shock = config.shock
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
{config.ambient_material.gamma:.8g}       0.72         {config.reynolds_number:.8g}          {config.characteristic_length:.8g}
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
4                                                  {config.cfl:.8g}       {config.dt:.8g}          30              0.000001
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
{config.final_time:.8g}                 {config.max_iterations}          {config.wall_clock_limit}
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
TECPLOT:1(BIN),0(ASCII),PARAVIEW BIN:2 ||\\|| WRITE OUTPUT RATE (SEC) ||\\|| WRITE RESTART RATE(SEC) ||\\|| WRITE AVERAGE OUTPUT RATE(SEC) ||\\||PRINT THE STENCILS AT THE PROBE POSITION(0 NOW, 1 YES)
5                       {config.output_interval:.8g}         20000             50000                   0
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


def write_job_script(path: Path, config: CaseConfig) -> None:
    job_name = config.job_name or config.name
    path.write_text(
        f"""#!/usr/bin/env bash
#SBATCH --job-name={job_name}
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

time srun.awe -np "${{SLURM_NTASKS:-128}}" ./ucns3d_p > ucns3d.out 2> ucns3d.err
date -Iseconds > done
""",
        encoding="ascii",
    )
    path.chmod(0o755)


def write_notes(path: Path, config: CaseConfig) -> None:
    materials = material_list(config)
    mesh = config.mesh
    domain = config.domain
    lines = [
        f"# {config.name}",
        "",
        config.description,
        "",
        "Generated from `cases/generate_cases.py`.",
        "",
        "Case setup:",
        f"- Domain: x=[{domain.xmin:.8g}, {domain.xmax:.8g}], y=[{domain.ymin:.8g}, {domain.ymax:.8g}] m.",
        f"- Refined x band: [{domain.refined_xmin:.8g}, {domain.refined_xmax:.8g}] m.",
        f"- Requested refined-region h: {mesh.requested_h:.8g} m.",
        f"- Actual centre dx: {(domain.refined_xmax - domain.refined_xmin) / mesh.x_center_cells:.8g} m.",
        f"- Actual dy: {domain.height / mesh.y_cells:.8g} m.",
        f"- Mesh cells: x={mesh.x_cells}, y={mesh.y_cells}, total={mesh.cell_count}.",
        f"- Shock initially at x = {config.shock_position_x:.8g} m.",
        f"- Left ambient state: rho = {config.shock.rho1:.8g} kg/m3, p = {config.shock.p1:.8g} Pa, u = {config.shock.u1:.8g} m/s.",
        f"- Right ambient state: rho = {config.shock.rho2:.8g} kg/m3, p = {config.shock.p2:.8g} Pa, u = {config.shock.u2:.8g} m/s.",
        f"- Shock speed magnitude: {config.shock.shock_speed:.8g} m/s.",
        "",
        "Materials:",
    ]
    for i, material in enumerate(materials, start=1):
        lines.append(
            f"- {i}: {material.name}, rho = {material.density:.8g} kg/m3, "
            f"gamma = {material.gamma:.8g}, pinf = {material.pinf:.8g} Pa."
        )
    lines.extend(["", "Bubbles:"])
    for i, bubble in enumerate(config.bubbles, start=1):
        lines.append(
            f"- {i}: material={bubble.material.name}, center={fmt_vector(bubble.center)} m, "
            f"diameter={bubble.diameter:.8g} m, density={bubble.effective_density:.8g} kg/m3."
        )
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_mesh_for_case(path: Path, config: CaseConfig) -> None:
    domain = config.domain
    mesh = config.mesh
    xs = piecewise_x(
        domain.xmin,
        domain.xmax,
        domain.refined_xmin,
        domain.refined_xmax,
        mesh.x_cells,
        mesh.x_left_cells,
        mesh.x_center_cells,
        mesh.x_right_cells,
    )
    ys = linspace(domain.ymin, domain.ymax, mesh.y_cells)
    write_mesh(path, xs, ys)


def validate_config(config: CaseConfig) -> None:
    if not config.bubbles:
        raise ValueError("case 407 generation requires at least one bubble")
    if config.final_time <= 0.0:
        raise ValueError("final_time must be positive")
    if config.output_interval <= 0.0:
        raise ValueError("output_interval must be positive")
    if config.characteristic_length <= 0.0:
        raise ValueError("characteristic_length must be positive")
    if config.mesh.requested_h <= 0.0 or config.mesh.cell_count < 1:
        raise ValueError("mesh resolution must be positive")
    for i, bubble in enumerate(config.bubbles, start=1):
        if bubble.diameter <= 0.0:
            raise ValueError(f"bubble {i} diameter must be positive")
        if len(bubble.center) != 3:
            raise ValueError(f"bubble {i} center must have 3 components")
        if len(bubble.velocity) != 3:
            raise ValueError(f"bubble {i} velocity must have 3 components")
        if bubble.effective_density <= 0.0:
            raise ValueError(f"bubble {i} density must be positive")


def generate_case(root: Path, config: CaseConfig) -> Path:
    validate_config(config)
    case_dir = root / config.name
    case_dir.mkdir(parents=True, exist_ok=True)

    write_mesh_for_case(case_dir / "grid.msh", config)
    write_multispecies(case_dir / "MULTISPECIES.DAT", config)
    write_407(case_dir / "407.nml", config)
    (case_dir / "UCNS3D.DAT").write_text(ucns3d_dat(config), encoding="ascii")
    write_job_script(case_dir / "ucns3d.jcf", config)
    write_notes(case_dir / "README.md", config)

    return case_dir


def material_from_dict(data: dict[str, Any]) -> Material:
    return Material(
        name=data["name"],
        gamma=float(data["gamma"]),
        density=float(data["density"]),
        sound_speed=None if data.get("sound_speed") is None else float(data["sound_speed"]),
        pinf=float(data.get("pinf", 0.0)),
    )


def config_from_dict(data: dict[str, Any]) -> CaseConfig:
    materials = {item["name"]: material_from_dict(item) for item in data["materials"]}
    ambient = materials[data["ambient_material"]]
    shock_data = data.get("shock", {})
    if "mach" in shock_data:
        shock = normal_shock_state(float(shock_data["mach"]), ambient, float(shock_data["pressure"]))
    else:
        shock = ShockState(
            p1=float(shock_data["p1"]),
            rho1=float(shock_data["rho1"]),
            u1=float(shock_data.get("u1", 0.0)),
            p2=float(shock_data["p2"]),
            rho2=float(shock_data["rho2"]),
            u2=float(shock_data["u2"]),
            shock_speed=float(shock_data["shock_speed"]),
        )

    domain_data = data["domain"]
    domain = Domain(
        xmin=float(domain_data["xmin"]),
        xmax=float(domain_data["xmax"]),
        ymin=float(domain_data.get("ymin", 0.0)),
        ymax=float(domain_data["ymax"]),
        refined_xmin=float(domain_data["refined_xmin"]),
        refined_xmax=float(domain_data["refined_xmax"]),
    )
    mesh_data = data["mesh"]
    if "h" in mesh_data:
        mesh = mesh_resolution_from_h(domain, float(mesh_data["h"]), float(mesh_data.get("buffer_factor", 2.0)))
    else:
        mesh = MeshResolution(
            requested_h=float(mesh_data["requested_h"]),
            buffer_factor=float(mesh_data.get("buffer_factor", 1.0)),
            y_cells=int(mesh_data["y_cells"]),
            x_left_cells=int(mesh_data["x_left_cells"]),
            x_center_cells=int(mesh_data["x_center_cells"]),
            x_right_cells=int(mesh_data["x_right_cells"]),
        )

    bubbles = tuple(
        Bubble(
            material=materials[item["material"]],
            center=tuple(float(value) for value in item["center"]),
            diameter=float(item["diameter"]),
            density=None if item.get("density") is None else float(item["density"]),
            pressure=None if item.get("pressure") is None else float(item["pressure"]),
            velocity=tuple(float(value) for value in item.get("velocity", (0.0, 0.0, 0.0))),
            perturbation_amplitude=float(item.get("perturbation_amplitude", 0.0)),
            perturbation_modes=int(item.get("perturbation_modes", 0)),
            perturbation_phase=float(item.get("perturbation_phase", 0.0)),
        )
        for item in data["bubbles"]
    )

    return CaseConfig(
        name=data["name"],
        description=data.get("description", data["name"]),
        ambient_material=ambient,
        shock=shock,
        domain=domain,
        mesh=mesh,
        shock_position_x=float(data["shock_position_x"]),
        final_time=float(data["final_time"]),
        output_interval=float(data["output_interval"]),
        bubbles=bubbles,
        characteristic_length=float(data["characteristic_length"]),
        reynolds_number=float(data.get("reynolds_number", 3900.0)),
        cfl=float(data.get("cfl", 1.4)),
        dt=float(data.get("dt", 1.9)),
        max_iterations=int(data.get("max_iterations", 100000000)),
        wall_clock_limit=int(data.get("wall_clock_limit", 432000)),
        job_name=data.get("job_name"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="JSON case description.")
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = config_from_dict(json.loads(args.config.read_text(encoding="ascii")))
    case_dir = generate_case(args.output_dir, config)
    print(f"{case_dir} (cells={config.mesh.cell_count})")


if __name__ == "__main__":
    main()
