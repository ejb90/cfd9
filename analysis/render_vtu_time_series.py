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
import tempfile
from pathlib import Path

import numpy as np
from render_vtu_plots import add_render_arguments, read_vtu_time_value
from track_interfaces import extract_interface_positions_vtk

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
    parser.add_argument(
        "--bubble-crop-component",
        type=int,
        metavar="N",
        help=(
            "track volume_fraction<N> over the full run and crop each frame to the largest bubble x extent; "
            "the crop follows each frame's bubble midpoint"
        ),
    )
    parser.add_argument(
        "--bubble-crop-cutoff",
        type=float,
        metavar="F",
        help="volume-fraction cutoff for --bubble-crop-component (default: --interface-cutoff)",
    )
    parser.add_argument(
        "--gif",
        "--gifs",
        "--make-gifs",
        dest="gifs",
        action="store_true",
        help="assemble one ordered animated GIF per requested plot after rendering",
    )
    parser.add_argument(
        "--gif-delay",
        type=int,
        default=6,
        metavar="CENTISECONDS",
        help="GIF frame delay in centiseconds (default: 6)",
    )
    parser.add_argument(
        "--shared-limits",
        action="store_true",
        help=(
            "query all selected VTUs first, then use one common colour range for each requested plot"
        ),
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
    if args.bubble_crop_component is not None and args.bubble_crop_component < 1:
        parser.error("--bubble-crop-component must be at least 1")
    if args.bubble_crop_cutoff is not None and not 0.0 < args.bubble_crop_cutoff < 1.0:
        parser.error("--bubble-crop-cutoff must lie strictly between 0 and 1")
    if args.gif_delay < 1:
        parser.error("--gif-delay must be at least 1 centisecond")
    if args.legend_mode == "separate" and not args.shared_limits:
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
    bounds: tuple[float, float, float, float] | None,
    limits: dict[str, list[float]] | None = None,
    ranges_only: bool = False,
) -> None:
    command.extend(["--plots", *args.plots, "--prefix", child_prefix, "--width", str(args.width)])
    if args.height is not None:
        command.extend(["--height", str(args.height)])
    if bounds is not None:
        command.extend(["--bounds", *(str(value) for value in bounds)])
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
    selected_limits = limits
    if selected_limits is None:
        selected_limits = {
            name: [float(lower), float(upper)] for name, lower, upper in args.limits or []
        }
    for name, (lower, upper) in selected_limits.items():
        command.extend(["--limits", name, str(lower), str(upper)])
    if args.visit is not None:
        command.extend(["--visit", str(args.visit.expanduser().resolve())])
    if args.magick is not None:
        command.extend(["--magick", str(args.magick.expanduser().resolve())])
    if args.overwrite:
        command.append("--overwrite")
    if ranges_only:
        command.append("--ranges-only")


def unique_paths(frames: list[dict[str, object]]) -> list[Path]:
    selected: list[Path] = []
    seen: set[Path] = set()
    for frame in frames:
        path = Path(frame["vtu"])
        if path not in seen:
            seen.add(path)
            selected.append(path)
    return selected


def shared_colour_limits(
    args: argparse.Namespace,
    single_renderer: Path,
    selected_paths: list[Path],
    frames: list[dict[str, object]],
) -> dict[str, list[float]]:
    """Preflight raw VisIt ranges and return fixed ranges for the full series."""
    explicit = {name: [float(lower), float(upper)] for name, lower, upper in args.limits or []}
    ranges: dict[str, list[tuple[float, float]]] = {name: [] for name in args.plots if name not in explicit}
    if not ranges:
        return explicit

    with tempfile.TemporaryDirectory(prefix="cfd9-vtu-ranges-") as temporary:
        temporary_dir = Path(temporary)
        for index, path in enumerate(selected_paths):
            prefix = f"range_{index:06d}"
            command = [sys.executable, str(single_renderer), str(path), str(temporary_dir)]
            frame = next(frame for frame in frames if Path(frame["vtu"]) == path)
            bounds = tuple(frame["bubble_crop_bounds"]) if "bubble_crop_bounds" in frame else args.bounds
            append_render_options(command, args, prefix, "none", bounds, limits={}, ranges_only=True)
            completed = subprocess.run(command, check=False, text=True, capture_output=True)
            if completed.returncode:
                diagnostic = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
                if diagnostic:
                    diagnostic = f"\nRenderer output:\n{diagnostic[-4000:]}"
                raise ValueError(
                    f"range query failed for {path} with exit status {completed.returncode}{diagnostic}"
                )
            manifest_path = temporary_dir / f"{prefix}_plots.json"
            try:
                manifest = json.loads(manifest_path.read_text())
                plots = manifest["plots"]
                for name in ranges:
                    lower, upper = plots[name]["data_range"]
                    lower, upper = float(lower), float(upper)
                    if not (math.isfinite(lower) and math.isfinite(upper) and lower <= upper):
                        raise ValueError(f"invalid data range for {name}: {lower}, {upper}")
                    ranges[name].append((lower, upper))
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"could not read range query output for {path}: {exc}") from exc

    shared = explicit.copy()
    for name, values in ranges.items():
        if not values:
            raise ValueError(f"range query produced no values for {name}")
        lower = min(value[0] for value in values)
        upper = max(value[1] for value in values)
        if name == "schlieren":
            shared[name] = [0.0, max(upper, 1.0e-12)]
        elif name == "vorticity":
            magnitude = max(abs(lower), abs(upper), 1.0e-12)
            shared[name] = [-magnitude, magnitude]
        elif name == "mixedness":
            shared[name] = [0.0, 1.0]
        elif lower < upper:
            shared[name] = [lower, upper]
        else:
            padding = max(abs(lower) * 1.0e-6, 1.0e-12)
            shared[name] = [lower - padding, upper + padding]
    return shared


def vtu_y_bounds(path: Path) -> tuple[float, float]:
    """Read a VTU's y extents for a bubble-following x crop."""
    import vtk

    reader = vtk.vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    bounds = reader.GetOutput().GetBounds()
    if len(bounds) < 4 or not all(math.isfinite(value) for value in bounds[2:4]) or bounds[2] >= bounds[3]:
        raise ValueError(f"could not determine valid y bounds from {path}")
    return float(bounds[2]), float(bounds[3])


def add_bubble_crop_bounds(args: argparse.Namespace, run_dir: Path, frames: list[dict[str, object]]) -> float | None:
    """Attach a constant-width, bubble-centred view to every selected frame."""
    if args.bubble_crop_component is None:
        return None

    cutoff = args.bubble_crop_cutoff if args.bubble_crop_cutoff is not None else args.interface_cutoff
    positions = extract_interface_positions_vtk(run_dir, args.bubble_crop_component, cutoff)
    if not len(positions):
        raise ValueError("bubble tracking found no cells above the requested volume-fraction cutoff")

    extent_start = np.min(positions[:, 1:4], axis=1)
    extent_end = np.max(positions[:, 1:4], axis=1)
    width = float(np.max(extent_end - extent_start))
    if not math.isfinite(width) or width <= 0.0:
        raise ValueError("bubble tracking did not produce a positive finite x extent")

    for frame in frames:
        time = frame["physical_time"]
        if time is None:
            raise ValueError(f"bubble crop requires a readable TimeValue: {frame['vtu']}")
        closest = int(np.argmin(np.abs(positions[:, 0] - time)))
        tracked_time = float(positions[closest, 0])
        if not np.isclose(tracked_time, time, rtol=1.0e-9, atol=1.0e-12):
            raise ValueError(f"no bubble-tracking position matches {frame['vtu']} at time {time:.16g} s")
        midpoint = float(0.5 * (extent_start[closest] + extent_end[closest]))
        y_min, y_max = (args.bounds[2], args.bounds[3]) if args.bounds is not None else vtu_y_bounds(Path(frame["vtu"]))
        bounds = (midpoint - 0.5 * width, midpoint + 0.5 * width, y_min, y_max)
        frame["bubble_crop_bounds"] = list(bounds)
        frame["bubble_crop_midpoint"] = midpoint
    return width


def make_gifs(
    args: argparse.Namespace,
    frames: list[dict[str, object]],
    output_dir: Path,
) -> dict[str, str]:
    """Create one manifest-ordered animated GIF for every requested plot."""
    requested = args.magick.expanduser().resolve() if args.magick is not None else shutil.which("magick")
    if requested is None or not Path(requested).is_file():
        raise ValueError("--gifs requires ImageMagick; pass --magick /path/to/magick")

    animations: dict[str, str] = {}
    if any(frame.get("physical_time") is None for frame in frames):
        raise ValueError("GIF assembly requires an embedded physical TimeValue for every frame")
    ordered_frames = sorted(frames, key=lambda frame: float(frame["physical_time"]))
    for plot_name in args.plots:
        frames_for_plot: list[str] = []
        seen: set[Path] = set()
        for frame in ordered_frames:
            try:
                path = Path(frame["plots"][plot_name])
            except KeyError as exc:
                raise ValueError(f"existing series has no {plot_name!r} plot tiles") from exc
            if not path.is_file():
                raise ValueError(f"GIF frame is missing: {path}")
            if path not in seen:
                seen.add(path)
                frames_for_plot.append(str(path))
        target = output_dir / (f"{args.prefix}_{plot_name}.gif" if args.prefix else f"{plot_name}.gif")
        if target.exists():
            target.unlink()
        command = [
            str(requested),
            "-delay",
            str(args.gif_delay),
            "-loop",
            "0",
            "-dispose",
            "previous",
            *frames_for_plot,
            str(target),
        ]
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            raise ValueError(f"ImageMagick GIF assembly failed for {plot_name}")
        animations[plot_name] = str(target)
    return animations


def rebuild_existing_gifs(args: argparse.Namespace, series_manifest: Path, output_dir: Path) -> bool:
    """Reuse existing tiles and manifest when GIF-only work was requested."""
    if not args.gifs or args.shared_limits or args.overwrite or not series_manifest.is_file():
        return False
    try:
        manifest = json.loads(series_manifest.read_text())
        frames = manifest["frames"]
        animations = make_gifs(args, frames, output_dir)
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"GIF assembly failed: {exc}") from exc
    manifest["animations"] = animations
    manifest["gif_delay_centiseconds"] = args.gif_delay
    series_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Rebuilt {len(animations)} GIFs from existing tiles; series manifest: {series_manifest}")
    return True


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

    try:
        bubble_crop_width = add_bubble_crop_bounds(args, run_dir, frames)
    except ValueError as exc:
        raise SystemExit(f"Invalid bubble crop: {exc}") from exc

    output_dir = args.output_dir.expanduser().resolve() if args.output_dir is not None else run_dir / "plot_series"
    output_dir.mkdir(parents=True, exist_ok=True)
    series_name = f"{args.prefix}_time_series.json" if args.prefix else "time_series.json"
    series_manifest = output_dir / series_name
    if rebuild_existing_gifs(args, series_manifest, output_dir):
        return
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
    if args.shared_limits:
        try:
            shared_limits = shared_colour_limits(args, single_renderer, selected_paths, frames)
        except ValueError as exc:
            raise SystemExit(f"Could not determine shared colour limits: {exc}") from exc
        print(f"Using shared colour limits: {shared_limits}", flush=True)
    else:
        shared_limits = None
    for index, path in enumerate(selected_paths):
        child_prefix = f"{args.prefix}_{path.stem}" if args.prefix else path.stem
        command = [sys.executable, str(single_renderer), str(path), str(output_dir)]
        child_legend_mode = "separate" if args.legend_mode == "separate" and index == 0 else args.legend_mode
        if args.legend_mode == "separate" and index > 0:
            child_legend_mode = "none"
        frame = next(frame for frame in frames if Path(frame["vtu"]) == path)
        bounds = tuple(frame["bubble_crop_bounds"]) if "bubble_crop_bounds" in frame else args.bounds
        append_render_options(command, args, child_prefix, child_legend_mode, bounds, limits=shared_limits)
        completed = subprocess.run(command, check=False, text=True, capture_output=True)
        if completed.returncode:
            diagnostic = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
            if diagnostic:
                diagnostic = f"\nRenderer output:\n{diagnostic[-4000:]}"
            raise SystemExit(f"rendering failed for {path} with exit status {completed.returncode}{diagnostic}")
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

    try:
        animations = make_gifs(args, frames, output_dir) if args.gifs else {}
    except ValueError as exc:
        raise SystemExit(f"GIF assembly failed: {exc}") from exc

    manifest = {
        "schema_version": 1,
        "selector": selector,
        "run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "legend_mode": args.legend_mode,
        "shared_limits": shared_limits,
        "bubble_crop_width": bubble_crop_width,
        "legends": shared_legends,
        "animations": animations,
        "gif_delay_centiseconds": args.gif_delay if args.gifs else None,
        "frames": frames,
    }
    series_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Rendered {len(rendered_manifests)} unique VTUs; series manifest: {series_manifest}")


if __name__ == "__main__":
    main()
