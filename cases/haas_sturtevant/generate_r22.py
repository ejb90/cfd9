#!/usr/bin/env python3
"""Generate the Haas--Sturtevant convergent R22-cylinder case.

Experimental parameters are from Haas & Sturtevant (1987), DOI
10.1017/S0022112087002003 (``HS87``). The computational geometry follows
Terashima & Tryggvason (2009), figure 5, DOI 10.1016/j.jcp.2009.02.023
(``TT09``), which reproduces the same cylindrical experiment.
"""

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

# HS87 atmospheric test-section conditions; TT09 uses gamma=1.4 for air.
AIR = Material("air", gamma=1.4, density=1.198, sound_speed=344.0)

# HS87 gives rho=3.69 kg/m3 and c=184 m/s for R22 at atmospheric pressure
# and 25 C. gamma is derived from c^2=gamma*p/rho for UCNS3D's ideal-gas EOS.
R22_DENSITY = 3.69
R22_SOUND_SPEED = 184.0
R22_GAMMA = R22_DENSITY * R22_SOUND_SPEED**2 / 101_325.0
R22 = Material("r22", gamma=R22_GAMMA, density=R22_DENSITY, sound_speed=R22_SOUND_SPEED)

# HS87: 5 cm cylinder in an 8.9 cm square test section at atmospheric pressure.
# Model the complete cylinder rather than imposing symmetry through its centre.
AMBIENT_PRESSURE = 101_325.0
TEST_SECTION_HALF_HEIGHT = 0.0445
CYLINDER_DIAMETER = 0.05
CYLINDER_CENTER = (0.0, 0.0, 0.0)
SHOCK_POSITION_X = 0.050  # TT09 figure 5: a/2+b=25 mm+25 mm.
DOMAIN = Domain(
    xmin=-0.175,
    xmax=0.150,
    ymin=-TEST_SECTION_HALF_HEIGHT,
    ymax=TEST_SECTION_HALF_HEIGHT,
    refined_xmin=-0.050,
    refined_xmax=0.075,
)

# HS87 figure 11's final R22 image is 1020 us after impact. Include the TT09
# b=25 mm pre-impact travel time in UCNS3D's absolute final time.
LAST_POST_IMPACT_TIME = 1_020.0e-6
OUTPUT_INTERVAL = 5.0e-6  # Derived: ~24 dumps per incident-shock D crossing.
INVISCID_REYNOLDS_NUMBER = 1.0e12  # HS87/TT09 use the Euler equations.
CFL = 0.2  # TT09's documented shock--bubble CFL; conservative for this case.


def build_config(cells_per_diameter: float, buffer_factor: float) -> CaseConfig:
    h = CYLINDER_DIAMETER / cells_per_diameter
    # HS87 uses Ms=1.22; derive its Rankine--Hugoniot state from ambient air.
    shock = normal_shock_state(1.22, AIR, AMBIENT_PRESSURE)
    impact_delay = (SHOCK_POSITION_X - 0.5 * CYLINDER_DIAMETER) / shock.shock_speed
    return CaseConfig(
        name="r22_cylinder_ms122",
        description="Convergent R22-cylinder case, figure 11, Ms=1.22.",
        ambient_material=AIR,
        shock=shock,
        domain=DOMAIN,
        mesh=mesh_resolution_from_h(DOMAIN, h, buffer_factor),
        shock_position_x=SHOCK_POSITION_X,
        final_time=impact_delay + LAST_POST_IMPACT_TIME,
        output_interval=OUTPUT_INTERVAL,
        bubbles=(
            Bubble(
                material=R22,
                center=CYLINDER_CENTER,
                diameter=CYLINDER_DIAMETER,
            ),
        ),
        characteristic_length=CYLINDER_DIAMETER,
        reynolds_number=INVISCID_REYNOLDS_NUMBER,
        cfl=CFL,
        job_name="haas-r22",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=CASE_ROOT / "haas_sturtevant" / "generated")
    # A 300-cell diameter gives the target bubble ratio R/h = 150.
    # buffer-factor=1 keeps the default grid uniform.
    parser.add_argument("--cells-per-diameter", type=float, default=300.0)
    parser.add_argument("--buffer-factor", type=float, default=1.0)
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
