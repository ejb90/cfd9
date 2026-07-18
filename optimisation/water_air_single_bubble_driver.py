#!/usr/bin/env python3
"""Run a small two-objective optimisation of one air cavity in shocked water.

Purpose
-------
This is a deliberately simple end-to-end test of the pymoo/Slurm workflow. A
planar 1 GPa shock travels left-to-right through water and collapses one
cylindrical air cavity. The optimiser changes only the initial air density and
cavity radius. It is intended to establish that candidate generation, UCNS3D
submission, time-series post-processing, checkpointing, and Pareto ranking all
work before attempting a multi-cavity arrangement study.

The physical reference scale follows the canonical 1 mm-diameter, 1 GPa
water-air calculation in Hawker & Ventikos, *Journal of Fluid Mechanics* 701
(2012), 59--97, DOI 10.1017/jfm.2012.132. That paper does not optimise density
or radius; this parameterisation is a workflow exercise around its reference
scale, not a reproduction of a published optimisation.

Design variables
----------------
``bubble_density_kg_m3`` ranges from 0.5 to 2.0 kg/m3 around the nominal
1 kg/m3 air state. ``bubble_radius_mm`` ranges from 0.25 to 0.75 mm around the
paper's 0.5 mm reference radius. The shock, ambient water, initial pressure,
bubble centre, mesh spacing, domain, and target region remain fixed. Varying
radius therefore changes the amount of gas and is intentionally treated as a
design choice, while using a common physical mesh spacing makes resolution
comparisons between candidates meaningful.

Objectives
----------
The target is a fixed circular region in the water, centred 2 mm downstream of
the bubble centre with radius 0.5 mm. It does not overlap any permitted initial
cavity. NSGA-II minimises two values:

1. ``-Ap95_target``: maximise the peak-in-time 95th-percentile target pressure,
   normalised by the 1 GPa incident shock pressure;
2. ``Mbad_target``: minimise the maximum air volume fraction reaching the same
   target region.

The fixed target makes all candidates deliver pressure to the same physical
location. It also prevents the contamination objective being trivially equal to
one at the initial time, which would happen if the target were the bubble itself.
The 95th percentile is preferred to a raw cell maximum for robustness.

Numerical scope
---------------
The default mesh uses 80 cells per 1 mm reference diameter and contains 208,000
cells. Across the radius bounds this gives 40--120 cells across the actual
diameter. This is a screening calculation: promising Pareto points should be
rerun at successively finer fixed physical spacings. The 20 ns output cadence
resolves the sub-microsecond collapse while remaining practical for a small
population. Water uses the repository's stiffened-gas model and air is ideal;
pressure trends are the intended result, not plasma temperature predictions.

Use ``--prepare-only`` to inspect candidates, then ``--launch-controller`` for
the three-day serial controller described in ``optimisation/README.md``.
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analysis.compute_ucns3d_metrics import write_metrics_json  # noqa: E402
from cases.generate_cases import (  # noqa: E402
    Bubble,
    CaseConfig,
    Domain,
    Material,
    ShockState,
    mesh_resolution_from_h,
)
from optimisation.ucns3d_pymoo import (  # noqa: E402
    Parameter,
    add_common_arguments,
    launch_controller,
    run_optimisation,
    slurm_from_args,
)

AMBIENT_PRESSURE = 1.0e5
INCIDENT_SHOCK_PRESSURE = 1.0e9
PRESHOCK_WATER_DENSITY = 1000.0
POSTSHOCK_WATER_DENSITY = 1323.65
POSTSHOCK_WATER_SPEED = 681.58

WATER = Material("water", gamma=4.4, density=PRESHOCK_WATER_DENSITY, pinf=6.0e8)
AIR = Material("air", gamma=1.4, density=1.0, pinf=0.0)

REFERENCE_DIAMETER = 1.0e-3
DEFAULT_CELLS_PER_REFERENCE_DIAMETER = 80

DOMAIN = Domain(
    xmin=-3.0e-3,
    xmax=5.0e-3,
    ymin=-2.5e-3,
    ymax=2.5e-3,
    refined_xmin=-1.5e-3,
    refined_xmax=3.5e-3,
)

SHOCK_POSITION_X = -1.25e-3
FINAL_TIME = 3.0e-6
OUTPUT_INTERVAL = 20.0e-9
INVISCID_REYNOLDS_NUMBER = 1.0e12
CFL = 0.2

TARGET_CENTER = (2.0e-3, 0.0)
TARGET_RADIUS = 0.5e-3

PARAMETERS = (
    Parameter("bubble_density_kg_m3", 0.5, 2.0),
    Parameter("bubble_radius_mm", 0.25, 0.75),
)


def water_post_shock_state() -> ShockState:
    """Return the left post-shock/right ambient 1 GPa water state."""
    shock_speed = abs(
        POSTSHOCK_WATER_DENSITY
        * POSTSHOCK_WATER_SPEED
        / (POSTSHOCK_WATER_DENSITY - PRESHOCK_WATER_DENSITY)
    )
    return ShockState(
        p1=INCIDENT_SHOCK_PRESSURE,
        rho1=POSTSHOCK_WATER_DENSITY,
        u1=POSTSHOCK_WATER_SPEED,
        p2=AMBIENT_PRESSURE,
        rho2=PRESHOCK_WATER_DENSITY,
        u2=0.0,
        shock_speed=shock_speed,
    )


def make_case(
    values: dict[str, float],
    evaluation_index: int,
    *,
    cells_per_reference_diameter: int = DEFAULT_CELLS_PER_REFERENCE_DIAMETER,
) -> CaseConfig:
    """Map density and radius to a complete one-cavity UCNS3D case."""
    radius = values["bubble_radius_mm"] * 1.0e-3
    return CaseConfig(
        name=f"eval_{evaluation_index:06d}",
        description=(
            "Single cylindrical air cavity in water at the Hawker--Ventikos "
            "1 mm/1 GPa reference scale; density/radius optimisation trial."
        ),
        ambient_material=WATER,
        shock=water_post_shock_state(),
        domain=DOMAIN,
        mesh=mesh_resolution_from_h(
            DOMAIN,
            REFERENCE_DIAMETER / cells_per_reference_diameter,
            buffer_factor=2.0,
        ),
        shock_position_x=SHOCK_POSITION_X,
        final_time=FINAL_TIME,
        output_interval=OUTPUT_INTERVAL,
        bubbles=(
            Bubble(
                material=AIR,
                center=(0.0, 0.0, 0.0),
                diameter=2.0 * radius,
                density=values["bubble_density_kg_m3"],
                pressure=AMBIENT_PRESSURE,
            ),
        ),
        characteristic_length=2.0 * radius,
        reynolds_number=INVISCID_REYNOLDS_NUMBER,
        cfl=CFL,
        job_name=f"water-air-one-{evaluation_index:06d}",
    )


def objective(run_dir: Path, _values: dict[str, float]) -> tuple[float, float]:
    """Return pressure-amplification and air-contamination objectives."""
    shock = water_post_shock_state()
    metrics = write_metrics_json(
        {
            "output_dir": run_dir,
            "json_out": run_dir / "metrics.json",
            "pressure_field": "pressure",
            "bad_material_field": "volume_fraction2",
            "p_incident": INCIDENT_SHOCK_PRESSURE,
            "p0": AMBIENT_PRESSURE,
            "t_ref": REFERENCE_DIAMETER / shock.shock_speed,
            "target_region": {
                "type": "circle",
                "xc": TARGET_CENTER[0],
                "yc": TARGET_CENTER[1],
                "radius": TARGET_RADIUS,
            },
            "interaction_region": {
                "type": "box",
                "xmin": DOMAIN.refined_xmin,
                "xmax": DOMAIN.refined_xmax,
                "ymin": DOMAIN.ymin,
                "ymax": DOMAIN.ymax,
            },
        }
    )
    return -metrics["Ap95_target"], metrics["Mbad_target"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_arguments(parser)
    parser.add_argument(
        "--cells-per-reference-diameter",
        type=int,
        default=DEFAULT_CELLS_PER_REFERENCE_DIAMETER,
        help="Fixed physical mesh spacing; the default 80 gives 208,000 cells.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.cells_per_reference_diameter < 1:
        raise ValueError("--cells-per-reference-diameter must be positive")

    if args.launch_controller:
        if args.prepare_only:
            raise ValueError("--launch-controller cannot be combined with --prepare-only")
        job_id = launch_controller(
            driver=Path(__file__),
            argv=sys.argv[1:],
            work_dir=args.work_dir,
            wall_time=args.controller_time,
            partition=args.controller_partition,
        )
        print(f"submitted optimisation controller job {job_id}")
        print(f"controller script: {(args.work_dir / 'optimisation-controller.jcf').resolve()}")
        return

    run_optimisation(
        parameters=PARAMETERS,
        make_case=partial(
            make_case,
            cells_per_reference_diameter=args.cells_per_reference_diameter,
        ),
        objective=objective,
        n_obj=2,
        work_dir=args.work_dir,
        slurm=slurm_from_args(args),
        generations=args.generations,
        population=args.population,
        algorithm_name=args.algorithm,
        seed=args.seed,
        prepare_only=args.prepare_only,
        submit_jobs=args.submit,
        poll_interval=args.poll_interval,
        max_concurrent=args.max_concurrent,
        failure_penalty=args.failure_penalty,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
