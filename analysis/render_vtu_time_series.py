#!/usr/bin/env python3
"""Render plot tiles for selected VTUs in a UCNS3D time series."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from render_vtu_plots import add_render_arguments, read_vtu_time_value

OUTPUT_PATTERN = re.compile(r"^OUT_(\d+)\.vtu$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render consistently configured plot tiles for explicitly selected VTUs, "
            "nearest physical times, or OUT_<timestep>.vtu numbers."
        )
    )
    parser.add_argument("run_dir", type=Path, help="directory containing numbered OUT_*.vtu files")
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        help="flat tile output directory (default: <run directory>/plot_series)",
    )
    selectors = parser.add_mutually_exclusive_group(required=True)
    selectors.add_argument(
        "--files",
        nargs="+",
        type=Path,
        metavar="VTU",
        help="explicit VTU paths; relative paths are resolved below RUN_DIR",
    )
    selectors.add_argument(
        "--times",
        nargs="+",
        type=float,
        metavar="SECONDS",
        help="physical times in seconds; use the VTU with the nearest embedded TimeValue",
    )
    selectors.add_argument(
        "--timesteps",
        nargs="+",
        type=int,
        metavar="N",
        help="exact integer suffixes in OUT_<N>.vtu filenames",
    )
    parser.add_argument(
        "--max-time-error",
        type=float,
        metavar="SECONDS",
        help="reject a --times match farther than this absolute physical-time error",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the selected VTUs and physical times without rendering",
    )
    add_render_arguments(parser)
    for action in parser._actions:
        if action.dest == "prefix":
            action.help = "series prefix; child tile prefixes become PREFIX_<VTU stem>"
            break
    args = parser.parse_args()
    args.legend_mode = args.legend_mode or "embedded"
    if args.max_time_error is not None and args.max_time_error < 0.0:
        parser.error("--max-time-error must be non-negative")
    if args.times is not None and not all(math.isfinite(value) and value >= 0.0 for value in args.times):
        parser.error("--times entries must be finite and non-negative")
    if args.timesteps is not None and any(value < 0 for value in args.timesteps):
        parser.error("--timesteps entries must be non-negative")
    if args.legend_mode == "separate":
        fixed_plots = {values[0] for values in args.limits or []}
        missing_limits = sorted(set(args.plots).difference(fixed_plots | {"mixedness"}))
        if missing_limits:
            parser.error(
                "--legend-mode separate requires fixed --limits for every data-dependent plot; missing: {}".format(
                    ", ".join(missing_limits)
                )
            )
    return args


def output_number(path: Path) -> int | None:
    match = OUTPUT_PATTERN.fullmatch(path.name)
    return int(match.group(1)) if match else None


def discover_outputs(run_dir: Path) -> list[Path]:
    return sorted(
        (path.resolve() for path in run_dir.glob("OUT_*.vtu") if output_number(path) is not None),
        key=lambda path: output_number(path),
    )


def describe_vtu(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"VTU file does not exist: {path}")
    if path.suffix.lower() != ".vtu":
        raise ValueError(f"expected a .vtu file: {path}")
    return {
        "vtu": str(path),
        "output_index": output_number(path),
        "physical_time": read_vtu_time_value(path),
    }


def select_frames(args: argparse.Namespace, run_dir: Path) -> tuple[str, list[dict[str, object]]]:
    if args.files is not None:
        frames = []
        for requested in args.files:
            path = requested.expanduser()
            if not path.is_absolute():
                path = run_dir / path
            frame = describe_vtu(path.resolve())
            frame["requested_file"] = str(requested)
            frames.append(frame)
        return "files", frames

    outputs = discover_outputs(run_dir)
    if not outputs:
        raise ValueError(f"no numbered OUT_*.vtu files found in {run_dir}")

    if args.timesteps is not None:
        by_number = {output_number(path): path for path in outputs}
        missing = [number for number in args.timesteps if number not in by_number]
        if missing:
            available = ", ".join(str(output_number(path)) for path in outputs)
            raise ValueError(f"timesteps not found: {missing}; available suffixes: {available}")
        frames = []
        for number in args.timesteps:
            frame = describe_vtu(by_number[number])
            frame["requested_timestep"] = number
            frames.append(frame)
        return "timesteps", frames

    candidates = [describe_vtu(path) for path in outputs]
    candidates = [frame for frame in candidates if frame["physical_time"] is not None]
    if not candidates:
        raise ValueError(f"numbered VTUs in {run_dir} do not contain readable TimeValue fields")

    frames = []
    for target in args.times:
        frame = min(
            candidates,
            key=lambda candidate: (
                abs(candidate["physical_time"] - target),
                candidate["physical_time"],
                candidate["output_index"],
            ),
        ).copy()
        error = abs(frame["physical_time"] - target)
        if args.max_time_error is not None and error > args.max_time_error:
            raise ValueError(
                f"nearest VTU to {target:.16g} s is {frame['vtu']} at "
                f"{frame['physical_time']:.16g} s (error {error:.16g} s), exceeding "
                f"--max-time-error {args.max_time_error:.16g} s"
            )
        frame["requested_time"] = target
        frame["time_error"] = error
        frames.append(frame)
    return "times", frames


def append_render_options(
    command: list[str],
    args: argparse.Namespace,
    child_prefix: str,
    legend_mode: str,
) -> None:
    command.extend(["--plots", *args.plots, "--prefix", child_prefix, "--width", str(args.width)])
    if args.height is not None:
        command.extend(["--height", str(args.height)])
    if args.bounds is not None:
        command.extend(["--bounds", *(str(value) for value in args.bounds)])
    command.extend(
        [
            "--ambient-component",
            str(args.ambient_component),
            "--interface-cutoff",
            str(args.interface_cutoff),
        ]
    )
    if args.interface_components is not None:
        command.extend(["--interface-components", *(str(value) for value in args.interface_components)])
    if args.interfaces:
        command.append("--interfaces")
    command.extend(["--legend-mode", legend_mode])
    for name, lower, upper in args.limits or []:
        command.extend(["--limits", name, lower, upper])
    if args.visit is not None:
        command.extend(["--visit", str(args.visit.expanduser().resolve())])
    if args.magick is not None:
        command.extend(["--magick", str(args.magick.expanduser().resolve())])
    if args.overwrite:
        command.append("--overwrite")


def unique_paths(frames: list[dict[str, object]]) -> list[Path]:
    selected: list[Path] = []
    seen: set[Path] = set()
    for frame in frames:
        path = Path(frame["vtu"])
        if path not in seen:
            seen.add(path)
            selected.append(path)
    return selected


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"run directory does not exist: {run_dir}")
    try:
        selector, frames = select_frames(args, run_dir)
    except ValueError as exc:
        raise SystemExit(f"Invalid time-series selection: {exc}") from exc

    for position, frame in enumerate(frames):
        target = ""
        if "requested_time" in frame:
            target = f" requested={frame['requested_time']:.16g}s error={frame['time_error']:.3g}s"
        elif "requested_timestep" in frame:
            target = f" requested timestep={frame['requested_timestep']}"
        print(
            f"[{position}] {frame['vtu']} time={frame['physical_time']}s output={frame['output_index']}{target}",
            flush=True,
        )
    if args.dry_run:
        return

    output_dir = args.output_dir.expanduser().resolve() if args.output_dir is not None else run_dir / "plot_series"
    output_dir.mkdir(parents=True, exist_ok=True)
    series_name = f"{args.prefix}_time_series.json" if args.prefix else "time_series.json"
    series_manifest = output_dir / series_name
    shared_legend_paths = {
        name: output_dir / (f"{args.prefix}_{name}_legend.png" if args.prefix else f"{name}_legend.png")
        for name in args.plots
        if args.legend_mode == "separate"
    }
    series_outputs = [series_manifest, *shared_legend_paths.values()]
    collisions = [path for path in series_outputs if path.exists()]
    if collisions and not args.overwrite:
        names = "\n  ".join(str(path) for path in collisions)
        raise SystemExit(f"series output already exists; pass --overwrite to replace it:\n  {names}")
    if args.overwrite:
        for path in collisions:
            path.unlink()

    single_renderer = Path(__file__).with_name("render_vtu_plots.py").resolve()
    rendered_manifests: dict[Path, Path] = {}
    selected_paths = unique_paths(frames)
    for index, path in enumerate(selected_paths):
        child_prefix = f"{args.prefix}_{path.stem}" if args.prefix else path.stem
        command = [sys.executable, str(single_renderer), str(path), str(output_dir)]
        child_legend_mode = "separate" if args.legend_mode == "separate" and index == 0 else args.legend_mode
        if args.legend_mode == "separate" and index > 0:
            child_legend_mode = "none"
        append_render_options(command, args, child_prefix, child_legend_mode)
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            raise SystemExit(f"rendering failed for {path} with exit status {completed.returncode}")
        rendered_manifests[path] = output_dir / f"{child_prefix}_plots.json"

    shared_legends = {}
    if args.legend_mode == "separate":
        first_manifest = json.loads(rendered_manifests[selected_paths[0]].read_text())
        for name, target in shared_legend_paths.items():
            source = Path(first_manifest["plots"][name]["legend_file"])
            if not source.is_file():
                raise SystemExit(f"shared legend source is missing: {source}")
            shutil.copy2(source, target)
            source.unlink()
            first_manifest["plots"][name]["legend_file"] = str(target)
            shared_legends[name] = str(target)
        rendered_manifests[selected_paths[0]].write_text(json.dumps(first_manifest, indent=2, sort_keys=True) + "\n")

    for frame in frames:
        manifest_path = rendered_manifests[Path(frame["vtu"])]
        child_manifest = json.loads(manifest_path.read_text())
        frame["render_manifest"] = str(manifest_path)
        frame["plots"] = {name: plot["file"] for name, plot in child_manifest["plots"].items()}

    manifest = {
        "schema_version": 1,
        "selector": selector,
        "run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "legend_mode": args.legend_mode,
        "legends": shared_legends,
        "frames": frames,
    }
    series_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Rendered {len(rendered_manifests)} unique VTUs; series manifest: {series_manifest}")


if __name__ == "__main__":
    main()
