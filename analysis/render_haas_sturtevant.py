#!/usr/bin/env python3
"""Render numerical schlieren at Haas--Sturtevant experimental frame times.

The run's ``case.json`` supplies the initial shock position/speed and cylinder
geometry.  The impact time is the initial shock-to-near-cylinder-surface gap
divided by shock speed.  Experimental frame delays are measured from impact.
Additional rendering options are forwarded to ``render_vtu_time_series.py``.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXPERIMENTAL_POST_IMPACT_TIMES = {
    "helium": (983.0e-6,),  # Haas & Sturtevant (1987), figure 7.
    "r22": (1_020.0e-6,),  # Haas & Sturtevant (1987), figure 11.
}


@dataclass(frozen=True)
class HaasCase:
    experiment: str
    impact_time: float
    output_interval: float | None


def infer_experiment(case_data: dict[str, object], requested: str) -> str:
    if requested != "auto":
        return requested
    text = " ".join(
        [str(case_data.get("name", "")), str(case_data.get("description", ""))]
        + [str(item.get("material", "")) for item in case_data.get("bubbles", [])]
    ).lower()
    if "helium" in text:
        return "helium"
    if "r22" in text:
        return "r22"
    raise ValueError("could not infer helium or r22 from case.json; pass --experiment")


def read_case(path: Path, experiment: str) -> HaasCase:
    try:
        data = json.loads(path.read_text())
        shock = data["shock"]
        bubble = data["bubbles"][0]
        shock_x = float(shock["position_x"])
        shock_speed = abs(float(shock["shock_speed"]))
        centre_x = float(bubble["center"][0])
        radius = 0.5 * float(bubble["diameter"])
    except (IndexError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read Haas--Sturtevant geometry from {path}: {exc}") from exc
    gap = abs(shock_x - centre_x) - radius
    if not math.isfinite(gap) or not math.isfinite(shock_speed) or gap < 0.0 or shock_speed <= 0.0:
        raise ValueError("case.json contains an invalid initial shock-to-cylinder gap or shock speed")
    output_interval = data.get("solver", {}).get("output_interval")
    return HaasCase(
        experiment=infer_experiment(data, experiment),
        impact_time=gap / shock_speed,
        output_interval=float(output_interval) if output_interval is not None else None,
    )


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="completed Haas--Sturtevant run directory")
    parser.add_argument("output_dir", nargs="?", type=Path, help="rendered tile directory")
    parser.add_argument("--case-json", type=Path, help="case metadata (default: RUN_DIR/case.json)")
    parser.add_argument("--experiment", choices=("auto", "helium", "r22"), default="auto")
    parser.add_argument(
        "--post-impact-times",
        type=float,
        nargs="+",
        metavar="SECONDS",
        help="experimental frame delays after shock impact; defaults to the published final frame",
    )
    parser.add_argument(
        "--max-time-error",
        type=float,
        metavar="SECONDS",
        help="maximum allowed nearest-VTU timing error (default: just over half the output interval)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the timing calculation without rendering")
    args, render_options = parser.parse_known_args()
    valid_post_impact_times = args.post_impact_times is None or all(
        value >= 0.0 and math.isfinite(value) for value in args.post_impact_times
    )
    if not valid_post_impact_times:
        parser.error("--post-impact-times entries must be finite and non-negative")
    if args.max_time_error is not None and (args.max_time_error < 0.0 or not math.isfinite(args.max_time_error)):
        parser.error("--max-time-error must be finite and non-negative")
    return args, render_options


def main() -> None:
    args, render_options = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    case_json = args.case_json.expanduser().resolve() if args.case_json else run_dir / "case.json"
    try:
        case = read_case(case_json, args.experiment)
    except ValueError as exc:
        raise SystemExit(f"Invalid Haas--Sturtevant case: {exc}") from exc

    post_impact_times = args.post_impact_times or EXPERIMENTAL_POST_IMPACT_TIMES[case.experiment]
    absolute_times = [case.impact_time + value for value in post_impact_times]
    print(f"experiment: {case.experiment}")
    print(f"shock impact: {case.impact_time * 1e6:.6g} us after simulation start")
    for relative, absolute in zip(post_impact_times, absolute_times, strict=True):
        print(f"post-impact {relative * 1e6:.6g} us -> simulation time {absolute * 1e6:.6g} us")
    if args.dry_run:
        return

    renderer = Path(__file__).with_name("render_vtu_time_series.py")
    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else run_dir / "haas_sturtevant_plots"
    max_time_error = args.max_time_error
    if max_time_error is None and case.output_interval is not None:
        max_time_error = 0.51 * case.output_interval
    command = [
        sys.executable,
        str(renderer),
        str(run_dir),
        str(output_dir),
        "--times",
        *(str(value) for value in absolute_times),
    ]
    if max_time_error is not None:
        command.extend(["--max-time-error", str(max_time_error)])
    if "--plots" not in render_options:
        command.extend(["--plots", "schlieren"])
    if "--prefix" not in render_options:
        command.extend(["--prefix", f"haas_{case.experiment}"])
    command.extend(render_options)
    result = subprocess.run(command, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
