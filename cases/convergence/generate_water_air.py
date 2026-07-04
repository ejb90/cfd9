#!/usr/bin/env python3
"""Generate water/air bubble convergence cases.

The mesh levels use the simple total-cell-doubling sequence from
`meshing/generate_mesh_suites.py`. The case layout keeps the original two-bubble
He/Kr geometry from the cfd8 inputs, but uses the water/air thermodynamic
properties from the shock-collapsed air-bubble-in-water setup:

  water: rho=993.89 kg/m3, gamma=4.4, p_inf=6e8 Pa
  air:   rho=1.204 kg/m3, gamma=1.4, p_inf=0 Pa
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "meshing"))

from cases.generate_cases import (  # noqa: E402
    Bubble,
    CaseConfig,
    Domain,
    Material,
    MeshResolution,
    ShockState,
    generate_case,
)
from generate_mesh_suites import HALVING_SUITE, MeshSpec  # noqa: E402


AMBIENT_PRESSURE = 101_325.0
POST_SHOCK_PRESSURE = 1.0e9

WATER = Material("water", gamma=4.4, density=993.89, pinf=6.0e8)
AIR = Material("air", gamma=1.4, density=1.204, pinf=0.0)

DOMAIN = Domain(
    xmin=-0.25,
    xmax=0.25,
    ymin=0.0,
    ymax=0.10,
    refined_xmin=-0.15,
    refined_xmax=0.15,
)

BUBBLE_RADIUS = 0.025
BUBBLE_DIAMETER = 2.0 * BUBBLE_RADIUS
BUBBLE_CENTRES = (
    (-0.05, 0.05, 0.0),
    (0.05, 0.05, 0.0),
)


@dataclass(frozen=True)
class ConvergenceCase:
    spec: MeshSpec
    case_dir: Path


def water_post_shock_state() -> ShockState:
    """Return a left-postshock/right-ambient state for the case-407 namelist."""
    p_ratio = (POST_SHOCK_PRESSURE + WATER.pinf) / (AMBIENT_PRESSURE + WATER.pinf)
    beta = (WATER.gamma - 1.0) / (WATER.gamma + 1.0)
    rho_post = WATER.density * (p_ratio + beta) / (beta * p_ratio + 1.0)
    shock_speed = math.sqrt(
        (POST_SHOCK_PRESSURE - AMBIENT_PRESSURE)
        / (WATER.density * (1.0 - WATER.density / rho_post))
    )
    particle_speed = shock_speed * (1.0 - WATER.density / rho_post)
    return ShockState(
        p1=POST_SHOCK_PRESSURE,
        rho1=rho_post,
        u1=particle_speed,
        p2=AMBIENT_PRESSURE,
        rho2=WATER.density,
        u2=0.0,
        shock_speed=shock_speed,
    )


def mesh_from_spec(spec: MeshSpec) -> MeshResolution:
    return MeshResolution(
        requested_h=spec.central_h,
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
            "Water-background/air-bubble convergence case. Geometry follows the "
            "original two-bubble He/Kr setup; material properties follow the "
            "air-bubble-in-water shock-collapse case."
        ),
        ambient_material=WATER,
        shock=water_post_shock_state(),
        domain=DOMAIN,
        mesh=mesh_from_spec(spec),
        shock_position_x=-0.1,
        final_time=0.000983,
        output_interval=0.00001,
        bubbles=tuple(
            Bubble(
                material=AIR,
                center=centre,
                diameter=BUBBLE_DIAMETER,
                pressure=AMBIENT_PRESSURE,
            )
            for centre in BUBBLE_CENTRES
        ),
        characteristic_length=1.0,
        reynolds_number=3900.0,
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


def generate_cases(output_dir: Path, limit: int | None, executable: Path | None, copy_executable: bool) -> list[ConvergenceCase]:
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
    parser.add_argument("--output-dir", type=Path, default=Path("cases/convergence/generated/water_air"))
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
        print(f"{item.spec.name:<14} {item.spec.cell_count:>10} {item.spec.central_h:>12.6g} {item.case_dir}")


if __name__ == "__main__":
    main()
