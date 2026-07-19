#!/usr/bin/env python3
"""Render reusable, annotation-free plot tiles from one UCNS3D VTU file."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

PLOT_NAMES = ("density", "schlieren", "pressure", "vorticity", "mixedness")


def read_vtu_time_value(path: Path) -> float | None:
    """Read UCNS3D's appended Float64 ``TimeValue`` without a VTK dependency."""
    data = path.read_bytes()
    appended_tag = data.find(b"<AppendedData")
    header = data if appended_tag < 0 else data[:appended_tag]
    time_tag = next(
        (tag for tag in re.findall(rb"<DataArray\b[^>]*>", header) if b'Name="TimeValue"' in tag),
        None,
    )
    if time_tag is None:
        return None

    offset_match = re.search(rb'offset="([0-9]+)"', time_tag)
    format_match = re.search(rb'format="([^"]+)"', time_tag)
    if appended_tag < 0 or offset_match is None or format_match is None or format_match.group(1) != b"appended":
        return None

    root_tag_match = re.search(rb"<VTKFile\b[^>]*>", header)
    if root_tag_match is None:
        return None
    root_tag = root_tag_match.group(0)
    if b'encoding="base64"' in data[appended_tag : appended_tag + 200]:
        return None
    endian = ">" if b'byte_order="BigEndian"' in root_tag else "<"
    header_code = "Q" if b'header_type="UInt64"' in root_tag else "I"
    header_size = struct.calcsize(header_code)

    appended_open_end = data.find(b">", appended_tag)
    underscore = data.find(b"_", appended_open_end + 1)
    if underscore < 0:
        return None
    block = underscore + 1 + int(offset_match.group(1))
    if block + header_size + 8 > len(data):
        return None
    payload_size = struct.unpack(endian + header_code, data[block : block + header_size])[0]
    if payload_size < 8:
        return None
    return float(struct.unpack(endian + "d", data[block + header_size : block + header_size + 8])[0])


def add_render_arguments(parser: argparse.ArgumentParser) -> None:
    """Add options shared by the single-file and time-series launchers."""
    parser.add_argument(
        "--plots",
        nargs="+",
        choices=PLOT_NAMES,
        default=list(PLOT_NAMES),
        help="plot presets to render (default: all five)",
    )
    parser.add_argument("--prefix", help="output filename prefix (default: VTU stem)")
    parser.add_argument("--width", type=int, default=1600, help="PNG width in pixels (default: 1600)")
    parser.add_argument(
        "--height",
        type=int,
        help="PNG height in pixels (default: derive from the physical view aspect ratio)",
    )
    parser.add_argument(
        "--bounds",
        type=float,
        nargs=4,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX"),
        help="fixed physical view; default is the complete VTU spatial extent",
    )
    parser.add_argument(
        "--ambient-component",
        type=int,
        default=1,
        metavar="N",
        help="ambient volume-fraction component (default: 1)",
    )
    parser.add_argument(
        "--interface-components",
        type=int,
        nargs="+",
        metavar="N",
        help="components whose alpha contours are drawn (default: all non-ambient components)",
    )
    parser.add_argument(
        "--interface-cutoff",
        type=float,
        default=0.5,
        metavar="F",
        help="volume-fraction contour value (default: 0.5)",
    )
    parser.add_argument(
        "--interfaces",
        action="store_true",
        help="overlay volume-fraction contours (default: clean scalar tiles without contours)",
    )
    parser.add_argument(
        "--legend-mode",
        choices=("embedded", "separate", "none"),
        help=(
            "legend output: embed in every tile, save one image beside each tile, or omit "
            "(default for a single VTU: embedded)"
        ),
    )
    parser.add_argument(
        "--limits",
        action="append",
        nargs=3,
        metavar=("PLOT", "MIN", "MAX"),
        help="fixed colour limits; repeat for multiple plots, e.g. --limits pressure 1e5 1e9",
    )
    parser.add_argument(
        "--visit",
        type=Path,
        help="VisIt executable (default: visit on PATH, then /usr/local/visit/bin/visit)",
    )
    parser.add_argument(
        "--magick",
        type=Path,
        help="ImageMagick magick/convert executable used to trim plots and extract legends",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace existing tiles and manifest")
    parser.add_argument("--ranges-only", action="store_true", help=argparse.SUPPRESS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use VisIt to render five consistently framed PNG tiles from one VTU file."
    )
    parser.add_argument("vtu", type=Path, help="single .vtu file to render")
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        help="output directory (default: <VTU parent>/plots/<VTU stem>)",
    )
    add_render_arguments(parser)
    return parser.parse_args()


def find_visit(requested: Path | None) -> Path:
    if requested is not None:
        candidate = requested.expanduser().resolve()
    else:
        executable = shutil.which("visit")
        candidate = Path(executable) if executable else Path("/usr/local/visit/bin/visit")
    if not candidate.is_file():
        raise SystemExit(f"VisIt executable not found: {candidate}")
    return candidate


def find_magick(requested: Path | None) -> Path | None:
    """Locate ImageMagick's modern ``magick`` or legacy ``convert`` frontend."""
    if requested is not None:
        candidate = requested.expanduser().resolve()
        if not candidate.is_file():
            raise SystemExit(f"ImageMagick executable not found: {candidate}")
        return candidate
    executable = shutil.which("magick") or shutil.which("convert")
    return Path(executable) if executable else None


def trim_plot_tiles(magick: Path, output_dir: Path, prefix: str, plots: list[str]) -> None:
    """Remove VisIt's uniform white canvas margin without changing the plot content."""
    for plot_name in plots:
        source = output_dir / f"{prefix}_{plot_name}.png"
        temporary = source.with_name(f".{source.stem}.trim.png")
        result = subprocess.run(
            [str(magick), str(source), "-trim", "+repage", str(temporary)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode or not temporary.is_file():
            diagnostic = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
            raise SystemExit(f"ImageMagick trim failed for {source}{': ' + diagnostic if diagnostic else ''}")
        temporary.replace(source)


def parse_limits(values: list[list[str]] | None, parser_names: tuple[str, ...]) -> dict[str, list[float]]:
    limits: dict[str, list[float]] = {}
    for name, lower_text, upper_text in values or []:
        if name not in parser_names:
            choices = ", ".join(parser_names)
            raise SystemExit(f"unknown plot in --limits: {name!r}; choose from {choices}")
        try:
            lower, upper = float(lower_text), float(upper_text)
        except ValueError as exc:
            raise SystemExit(f"invalid numeric limits for {name}: {lower_text}, {upper_text}") from exc
        if not lower < upper:
            raise SystemExit(f"limits for {name} must satisfy MIN < MAX")
        limits[name] = [lower, upper]
    return limits


def main() -> None:
    args = parse_args()
    legend_mode = args.legend_mode or "embedded"
    vtu = args.vtu.expanduser().resolve()
    if not vtu.is_file():
        raise SystemExit(f"VTU file does not exist: {vtu}")
    if vtu.suffix.lower() != ".vtu":
        raise SystemExit(f"expected a single .vtu file: {vtu}")
    if args.width <= 0 or (args.height is not None and args.height <= 0):
        raise SystemExit("--width and --height must be positive")
    if args.ambient_component < 1:
        raise SystemExit("--ambient-component must be at least 1")
    if not 0.0 < args.interface_cutoff < 1.0:
        raise SystemExit("--interface-cutoff must lie strictly between 0 and 1")
    if args.bounds is not None and not (args.bounds[0] < args.bounds[1] and args.bounds[2] < args.bounds[3]):
        raise SystemExit("--bounds must satisfy XMIN < XMAX and YMIN < YMAX")

    output_dir = (
        args.output_dir.expanduser().resolve() if args.output_dir is not None else vtu.parent / "plots" / vtu.stem
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or vtu.stem
    if Path(prefix).name != prefix:
        raise SystemExit("--prefix must be a filename prefix, not a path")

    expected = [] if args.ranges_only else [output_dir / f"{prefix}_{name}.png" for name in args.plots]
    if legend_mode == "separate":
        expected.extend(output_dir / f"{prefix}_{name}_legend.png" for name in args.plots)
    expected.append(output_dir / f"{prefix}_plots.json")
    collisions = [path for path in expected if path.exists()]
    if collisions and not args.overwrite:
        names = "\n  ".join(str(path) for path in collisions)
        raise SystemExit(f"output already exists; pass --overwrite to replace it:\n  {names}")
    if args.overwrite:
        for path in collisions:
            path.unlink()

    components = args.interface_components
    if components is not None:
        if any(component < 1 for component in components):
            raise SystemExit("--interface-components entries must be at least 1")
        if len(set(components)) != len(components):
            raise SystemExit("--interface-components contains duplicates")

    config = {
        "schema_version": 1,
        "vtu": str(vtu),
        "output_dir": str(output_dir),
        "prefix": prefix,
        "plots": args.plots,
        "width": args.width,
        "height": args.height,
        "bounds": args.bounds,
        "ambient_component": args.ambient_component,
        "interface_components": components,
        "interface_cutoff": args.interface_cutoff,
        "draw_interfaces": args.interfaces,
        "legend_mode": legend_mode,
        "ranges_only": args.ranges_only,
        "limits": parse_limits(args.limits, PLOT_NAMES),
        "physical_time": read_vtu_time_value(vtu),
        "output_index": int(match.group(1)) if (match := re.search(r"([0-9]+)$", vtu.stem)) else None,
    }

    visit = find_visit(args.visit)
    visit_script = Path(__file__).with_name("render_vtu.visit.py").resolve()
    if not visit_script.is_file():
        raise SystemExit(f"VisIt rendering script is missing: {visit_script}")

    with tempfile.TemporaryDirectory(prefix="cfd9-visit-render-") as temporary:
        config_path = Path(temporary) / "render_config.json"
        config_path.write_text(json.dumps(config, indent=2) + "\n")
        command = [
            str(visit),
            "-nowin",
            "-cli",
            "-noconfig",
            "-nowindowmetrics",
            "-s",
            str(visit_script),
            str(config_path),
        ]
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
        )

    # VisIt 3.4 maps sys.exit(0) from a startup script to frontend status 250.
    # Report its own diagnostic before attempting ImageMagick post-processing.
    successful_status = completed.returncode in (0, 250)
    if not successful_status:
        diagnostic = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if diagnostic:
            diagnostic = f"\nVisIt output:\n{diagnostic[-4000:]}"
        raise SystemExit(f"VisIt rendering failed with exit status {completed.returncode}{diagnostic}")

    magick = None if args.ranges_only else find_magick(args.magick)
    if not args.ranges_only and magick is None:
        raise SystemExit("trimming plot whitespace requires ImageMagick; pass --magick /path/to/magick-or-convert")
    if legend_mode == "separate":
        if magick is None:
            raise SystemExit("separate legends require ImageMagick; pass --magick /path/to/magick-or-convert")
        for plot_name in args.plots:
            source = output_dir / f"{prefix}_{plot_name}_legend_source.png"
            target = output_dir / f"{prefix}_{plot_name}_legend.png"
            if not source.is_file():
                raise SystemExit(f"VisIt did not write the expected legend source: {source}")
            crop = subprocess.run(
                [
                    str(magick),
                    str(source),
                    "-crop",
                    "280x600+520+0",
                    "+repage",
                    "-trim",
                    "+repage",
                    "-bordercolor",
                    "white",
                    "-border",
                    "12",
                    str(target),
                ],
                check=False,
            )
            if crop.returncode:
                raise SystemExit(f"ImageMagick legend extraction failed for {source}")
            source.unlink()
    if not args.ranges_only:
        trim_plot_tiles(magick, output_dir, prefix, args.plots)
    manifest = output_dir / f"{prefix}_plots.json"
    missing_outputs = [path for path in expected if not path.is_file()]
    if missing_outputs:
        missing = ", ".join(str(path) for path in missing_outputs) or "none"
        raise SystemExit(f"VisIt did not write the expected outputs: {missing}")
    print(f"Rendered {len(args.plots)} plot tiles; manifest: {manifest}")


if __name__ == "__main__":
    main()
