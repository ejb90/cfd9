#!/usr/bin/env python3
"""Generate the Haas-Sturtevant convergent R22-cylinder case."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASE_ROOT))

from generate_cases import (  # noqa: E402
    Bubble,
    CaseConfig,
    Domain,
    Material,
    generate_case,
    mesh_resolution_from_h,
    normal_shock_state,
)


AIR = Material("air", gamma=1.4, density=1.198, sound_speed=344.0)

# Paper value: R22 vapour density 3.69 kg/m3 and sound speed 184 m/s at
# atmospheric pressure and 25 C. gamma is chosen to remain close to that sound
# speed under the ideal/stiffened-gas p_inf=0 model used here.
R22 = Material("r22", gamma=1.17, density=3.69, sound_speed=184.0)

AMBIENT_PRESSURE = 101_325.0
TEST_SECTION_HEIGHT = 0.089
CYLINDER_DIAMETER = 0.05
CYLINDER_CENTER = (0.0, TEST_SECTION_HEIGHT / 2.0, 0.0)
DOMAIN = Domain(
    xmin=-0.35,
    xmax=0.25,
    ymin=0.0,
    ymax=TEST_SECTION_HEIGHT,
    refined_xmin=-0.050,
    refined_xmax=0.055,
)


def build_config(cells_per_diameter: float, buffer_factor: float) -> CaseConfig:
    h = CYLINDER_DIAMETER / cells_per_diameter
    shock = normal_shock_state(1.22, AIR, AMBIENT_PRESSURE)
    return CaseConfig(
        name="r22_cylinder_ms122",
        description="Convergent R22-cylinder case, figure 11, Ms=1.22.",
        ambient_material=AIR,
        shock=shock,
        domain=DOMAIN,
        mesh=mesh_resolution_from_h(DOMAIN, h, buffer_factor),
        shock_position_x=0.100,
        final_time=1_020.0e-6,
        output_interval=10.0e-6,
        bubbles=(
            Bubble(
                material=R22,
                center=CYLINDER_CENTER,
                diameter=CYLINDER_DIAMETER,
            ),
        ),
        characteristic_length=CYLINDER_DIAMETER,
        job_name="haas-r22",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=CASE_ROOT / "haas_sturtevant" / "generated")
    parser.add_argument("--cells-per-diameter", type=float, default=100.0)
    parser.add_argument("--buffer-factor", type=float, default=2.0)
    args = parser.parse_args()
    if args.cells_per_diameter <= 0.0:
        parser.error("--cells-per-diameter must be positive")
    if args.buffer_factor < 1.0:
        parser.error("--buffer-factor must be >= 1")
    return args


def main() -> None:
    args = parse_args()
    config = build_config(args.cells_per_diameter, args.buffer_factor)
    case_dir = generate_case(args.output_dir, config)
    print(f"{case_dir} (h={config.mesh.requested_h:.6g}, cells={config.mesh.cell_count})")


if __name__ == "__main__":
    main()
