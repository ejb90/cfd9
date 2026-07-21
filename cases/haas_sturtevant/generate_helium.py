#!/usr/bin/env python3
"""Generate the Haas--Sturtevant divergent helium-cylinder case.

Experimental parameters are from Haas & Sturtevant (1987), DOI
10.1017/S0022112087002003 (``HS87``). The computational geometry and initial
state convention follow Terashima & Tryggvason (2009), section 4.1 and figure 5,
DOI 10.1016/j.jcp.2009.02.023 (``TT09``).
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

# HS87: atmospheric air in the 8.9 cm test section. The 1.198 kg/m3 density
# and 344 m/s sound speed are the 25 C atmospheric values used to dimensionalise
# the experiment; gamma=1.4 is the perfect-gas value used by TT09 section 4.1.
AIR = Material("air", gamma=1.4, density=1.198, sound_speed=344.0)

# HS87 section 4 notes air contamination and estimates 833 m/s for the Ms=1.22
# helium cylinder. rho=0.216 kg/m3 is the reported contaminated-mixture value.
# gamma is derived from c^2=gamma*p/rho at the atmospheric pressure below.
HELIUM_DENSITY = 0.216
HELIUM_SOUND_SPEED = 833.0
HELIUM_GAMMA = HELIUM_DENSITY * HELIUM_SOUND_SPEED**2 / 101_325.0
HELIUM_MIX = Material(
    "helium_mixture",
    gamma=HELIUM_GAMMA,
    density=HELIUM_DENSITY,
    sound_speed=HELIUM_SOUND_SPEED,
)

# HS87: 5 cm cylinder in an 8.9 cm square test section at atmospheric pressure.
# Model the complete cylinder rather than imposing symmetry through its centre.
AMBIENT_PRESSURE = 101_325.0
TEST_SECTION_HALF_HEIGHT = 0.0445
CYLINDER_DIAMETER = 0.05
CYLINDER_CENTER = (0.0, 0.0, 0.0)

# TT09 figure 5: a=50 mm, b=25 mm, c=100 mm, d=325 mm. With the cylinder
# centred at x=0 this gives shock x=50 mm and domain x=[-175, 150] mm.
SHOCK_POSITION_X = 0.050
DOMAIN = Domain(
    xmin=-0.175,
    xmax=0.150,
    ymin=-TEST_SECTION_HALF_HEIGHT,
    ymax=TEST_SECTION_HALF_HEIGHT,
    refined_xmin=-0.050,
    refined_xmax=0.075,
)

# HS87 figure 7's final helium image is 983 us after impact. The added term is
# the TT09 b=25 mm initial shock-to-cylinder gap divided by the shock speed.
LAST_POST_IMPACT_TIME = 983.0e-6
# Derived output choice: ~24 dumps during one incident-shock crossing of D.
OUTPUT_INTERVAL = 5.0e-6
# HS87 and TT09 model the interaction with the Euler equations.
INVISCID_REYNOLDS_NUMBER = 1.0e12
# TT09 section 4.1 uses CFL=0.2 for its corresponding helium calculation.
CFL = 0.2


def build_config(cells_per_diameter: float, buffer_factor: float) -> CaseConfig:
    h = CYLINDER_DIAMETER / cells_per_diameter
    # HS87 uses Ms=1.22; the Rankine--Hugoniot state is derived by
    # normal_shock_state from the referenced ambient air values.
    shock = normal_shock_state(1.22, AIR, AMBIENT_PRESSURE)
    impact_delay = (SHOCK_POSITION_X - 0.5 * CYLINDER_DIAMETER) / shock.shock_speed
    return CaseConfig(
        name="helium_cylinder_ms122",
        description="Divergent helium-cylinder case, figure 7, Ms=1.22.",
        ambient_material=AIR,
        shock=shock,
        domain=DOMAIN,
        mesh=mesh_resolution_from_h(DOMAIN, h, buffer_factor),
        shock_position_x=SHOCK_POSITION_X,
        final_time=impact_delay + LAST_POST_IMPACT_TIME,
        output_interval=OUTPUT_INTERVAL,
        bubbles=(
            Bubble(
                material=HELIUM_MIX,
                center=CYLINDER_CENTER,
                diameter=CYLINDER_DIAMETER,
            ),
        ),
        characteristic_length=CYLINDER_DIAMETER,
        reynolds_number=INVISCID_REYNOLDS_NUMBER,
        cfl=CFL,
        job_name="haas-helium",
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
