#!/usr/bin/env python3
"""Generate the Terashima--Tryggvason air-bubble-in-water benchmark.

Physical parameters are from Terashima & Tryggvason (2009), section 4.4,
pp. 4031--4033, DOI 10.1016/j.jcp.2009.02.023 (reference ``TT09`` below).
The mesh levels retain the repository's total-cell-doubling sequence, but the
geometry, material states, time window, and CFL now reproduce that benchmark.

The x-domain is padded relative to TT09 so the existing mesh names and square
cell progression remain valid. All interaction geometry is unchanged.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "meshing"))

from generate_mesh_suites import HALVING_SUITE, MeshSpec  # noqa: E402

from cases.generate_cases import (  # noqa: E402
    Bubble,
    CaseConfig,
    Domain,
    Material,
    MeshResolution,
    ShockState,
    generate_case,
)

# TT09 section 4.4: stiffened-gas constants and all three initial states.
AMBIENT_PRESSURE = 1.0e5
POST_SHOCK_PRESSURE = 1.0e9
PRESHOCK_WATER_DENSITY = 1000.0
POSTSHOCK_WATER_DENSITY = 1323.65
POSTSHOCK_WATER_VELOCITY = -681.58

WATER = Material("water", gamma=4.4, density=PRESHOCK_WATER_DENSITY, pinf=6.0e8)
AIR = Material("air", gamma=1.4, density=1.0, pinf=0.0)

# TT09 figure 5 and section 4.4: a=6.0 mm, b=1.2 mm, c=1.8 mm,
# d=15.0 mm, and e=6.0 mm. The published coordinates, with the bubble
# centred at x=0, are xmin=-9 mm, xmax=6 mm, and shock x=4.2 mm.
# We add 6 mm upstream and 3 mm downstream padding. This makes the x extent
# four times the half-domain height, matching HALVING_SUITE's nx/ny ratio and
# keeping cells approximately square without altering a, b, or the shock.
DOMAIN = Domain(
    xmin=-0.015,
    xmax=0.009,
    ymin=0.0,
    ymax=0.006,
    refined_xmin=-0.012,
    refined_xmax=0.006,
)

BUBBLE_DIAMETER = 0.006  # TT09 section 4.4, length a.
BUBBLE_CENTER = (0.0, 0.0, 0.0)  # TT09 uses the upper half-domain by symmetry.
SHOCK_POSITION_X = 0.5 * BUBBLE_DIAMETER + 0.0012  # TT09 figure 5, a/2 + b.

# TT09 figure 19 and figure 20 follow the collapse from 0 to 4 microseconds.
FINAL_TIME = 4.0e-6
# Derived output choice: 80 equal samples over the published interval and
# about 43 samples during one D/|shock speed| bubble-crossing time.
OUTPUT_INTERVAL = 0.05e-6

# TT09 section 4.4 uses the Euler equations. This large required UCNS3D input
# value makes viscosity negligible if a Navier--Stokes executable is used.
INVISCID_REYNOLDS_NUMBER = 1.0e12
# TT09 section 4.4 explicitly reports CFL=0.2 for this calculation.
CFL = 0.2


@dataclass(frozen=True)
class ConvergenceCase:
    spec: MeshSpec
    case_dir: Path


def water_post_shock_state() -> ShockState:
    """Return TT09's left ambient/right post-shock state."""
    # Derived from TT09's tabulated states by mass conservation across the
    # shock. ShockState stores a positive speed magnitude.
    shock_speed = abs(
        POSTSHOCK_WATER_DENSITY
        * POSTSHOCK_WATER_VELOCITY
        / (POSTSHOCK_WATER_DENSITY - PRESHOCK_WATER_DENSITY)
    )
    return ShockState(
        p1=AMBIENT_PRESSURE,
        rho1=PRESHOCK_WATER_DENSITY,
        u1=0.0,
        p2=POST_SHOCK_PRESSURE,
        rho2=POSTSHOCK_WATER_DENSITY,
        u2=POSTSHOCK_WATER_VELOCITY,
        shock_speed=shock_speed,
    )


def mesh_from_spec(spec: MeshSpec) -> MeshResolution:
    # HALVING_SUITE is a repository-derived convergence sequence. With the
    # TT09 half-domain height equal to one bubble diameter, y_cells is exactly
    # the number of cells per diameter. TT09 section 4.4/figure 20 reports
    # comparison grids at 80, 160, and 240 nodes per diameter.
    return MeshResolution(
        requested_h=BUBBLE_DIAMETER / spec.y_cells,
        buffer_factor=1.0,
        y_cells=spec.y_cells,
        x_left_cells=spec.x_left_cells,
        x_center_cells=spec.x_center_cells,
        x_right_cells=spec.x_right_cells,
    )


def build_case(spec: MeshSpec) -> CaseConfig:
    return CaseConfig(
        name=spec.name,
        description=(
            "Terashima--Tryggvason (2009), section 4.4, cylindrical "
            "air-bubble-in-water shock-collapse convergence case."
        ),
        ambient_material=WATER,
        shock=water_post_shock_state(),
        domain=DOMAIN,
        mesh=mesh_from_spec(spec),
        shock_position_x=SHOCK_POSITION_X,
        final_time=FINAL_TIME,
        output_interval=OUTPUT_INTERVAL,
        bubbles=(
            Bubble(
                material=AIR,
                center=BUBBLE_CENTER,
                diameter=BUBBLE_DIAMETER,
                pressure=AMBIENT_PRESSURE,
            ),
        ),
        characteristic_length=BUBBLE_DIAMETER,
        reynolds_number=INVISCID_REYNOLDS_NUMBER,
        cfl=CFL,
        job_name=spec.name,
    )


def stage_executable(case_dir: Path, executable: Path, copy: bool) -> None:
    source = executable.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"UCNS3D executable not found: {source}")
    if not source.stat().st_mode & 0o111:
        raise PermissionError(f"UCNS3D executable is not executable: {source}")
    target = case_dir / "ucns3d_p"
    if target.exists() or target.is_symlink():
        target.unlink()
    if copy:
        shutil.copy2(source, target)
    else:
        target.symlink_to(source)


def generate_cases(
    output_dir: Path,
    limit: int | None,
    executable: Path | None,
    copy_executable: bool,
) -> list[ConvergenceCase]:
    specs = HALVING_SUITE.specs if limit is None else HALVING_SUITE.specs[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for spec in specs:
        config = build_case(spec)
        case_dir = generate_case(output_dir, config)
        if executable is not None:
            stage_executable(case_dir, executable, copy_executable)
        written.append(ConvergenceCase(spec=spec, case_dir=case_dir))
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "cases" / "convergence" / "generated" / "water_air",
    )
    parser.add_argument("--limit", type=int, help="Generate only the first N mesh levels.")
    parser.add_argument("--ucns3d", type=Path, help="Optional ucns3d_p executable to symlink into each case.")
    parser.add_argument("--copy-executable", action="store_true", help="Copy ucns3d_p instead of symlinking it.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def main() -> None:
    args = parse_args()
    cases = generate_cases(args.output_dir, args.limit, args.ucns3d, args.copy_executable)
    print(f"{'case':<14} {'cells':>10} {'central_h':>12} path")
    for item in cases:
        actual_h = BUBBLE_DIAMETER / item.spec.y_cells
        print(f"{item.spec.name:<14} {item.spec.cell_count:>10} {actual_h:>12.6g} {item.case_dir}")


if __name__ == "__main__":
    main()
