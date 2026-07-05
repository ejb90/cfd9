#!/usr/bin/env python3
"""Compute robust UCNS3D shock-bubble objective metrics from VTU/PVTU output.

The metrics are intended for optimisation of pressure amplification and clean
compression, not for general visualisation. Results are written as a flat JSON
object so an external optimiser can read key/value pairs directly.
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv

DEFAULT_CONFIG: dict[str, Any] = {
    "output_dir": Path("."),
    "json_out": Path("metrics.json"),
    "pressure_field": "pressure",
    "bad_material_field": "volume_fraction",
    "area_field": None,
    "p_incident": 1.0,
    "p0": 1.0,
    "t_ref": 1.0,
    "target_region": None,
    "interaction_region": None,
}


@dataclass(frozen=True)
class Region:
    """A 2D target/interaction region."""

    kind: str
    values: tuple[float, ...]


@dataclass
class Histories:
    """Per-file metric histories used to compute final scalar objectives."""

    times: list[float]
    p95_target: list[float]
    mean_p_target: list[float]
    mbad_target: list[float]
    target_excess_integral: list[float]
    interaction_excess_integral: list[float]
    target_n_cells: int = 0
    interaction_n_cells: int = 0


class MetricsError(RuntimeError):
    """Raised when objective metrics cannot be computed from the requested data."""


def find_vtu_files(output_dir: Path) -> list[Path]:
    """Find `.pvtu` and `.vtu` files, sorted by timestep-like numeric filename parts."""
    if not output_dir.is_dir():
        raise MetricsError(f"output directory not found: {output_dir}")

    files = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".vtu", ".pvtu"} and not path.name.startswith(".")
    ]
    if not files:
        raise MetricsError(f"no .vtu or .pvtu files found in {output_dir}")

    pvtus = [path for path in files if path.suffix.lower() == ".pvtu"]
    if pvtus:
        return sorted(pvtus, key=timestep_sort_key)
    return sorted(files, key=timestep_sort_key)


def timestep_sort_key(path: Path) -> tuple[tuple[int, ...], str]:
    """Sort by all integer groups in the filename, then by name."""
    numbers = tuple(int(match) for match in re.findall(r"\d+", path.stem))
    return numbers, path.name


def read_time(mesh: pv.DataSet, fallback: float) -> float:
    """Read simulation time from field data, falling back to the supplied value."""
    for name in ("TimeValue", "TIME", "Time", "time"):
        if name not in mesh.field_data:
            continue
        values = np.asarray(mesh.field_data[name]).ravel()
        if values.size:
            return float(values[0])
    warnings.warn(f"no TimeValue field found; using fallback time {fallback}", RuntimeWarning, stacklevel=2)
    return float(fallback)


def get_cell_array(mesh: pv.DataSet, name: str) -> np.ndarray:
    """Return a named cell-data array as a 1D float array."""
    if name not in mesh.cell_data:
        available = ", ".join(mesh.cell_data.keys()) or "<none>"
        raise MetricsError(f"missing cell-data field '{name}'. Available cell data: {available}")
    values = np.asarray(mesh.cell_data[name], dtype=float)
    if values.ndim > 1:
        if values.shape[1] != 1:
            raise MetricsError(f"cell-data field '{name}' is not scalar; shape={values.shape}")
        values = values[:, 0]
    values = values.ravel()
    if values.size != mesh.n_cells:
        raise MetricsError(f"cell-data field '{name}' has {values.size} values for {mesh.n_cells} cells")
    return values


def get_cell_areas(mesh: pv.DataSet, area_field: str | None = None) -> np.ndarray:
    """Return cell areas, using an existing cell-data field or PyVista cell-size calculation."""
    candidate_fields = [area_field] if area_field else ["area", "cell_area", "Area"]
    for name in candidate_fields:
        if name and name in mesh.cell_data:
            areas = np.asarray(mesh.cell_data[name], dtype=float).ravel()
            if areas.size == mesh.n_cells and np.all(np.isfinite(areas)) and np.all(areas >= 0.0):
                return areas
            raise MetricsError(f"area field '{name}' is invalid for {mesh.n_cells} cells")

    try:
        sized = mesh.compute_cell_sizes(length=False, area=True, volume=False)
    except Exception as exc:  # noqa: BLE001
        raise MetricsError(f"failed to compute cell areas: {exc}") from exc

    if "Area" not in sized.cell_data:
        raise MetricsError("PyVista cell-size calculation did not produce an 'Area' field")
    areas = np.asarray(sized.cell_data["Area"], dtype=float).ravel()
    if areas.size != mesh.n_cells:
        raise MetricsError(f"computed {areas.size} areas for {mesh.n_cells} cells")
    if not np.all(np.isfinite(areas)) or np.any(areas < 0.0):
        raise MetricsError("computed cell areas contain non-finite or negative values")
    if float(np.sum(areas)) <= 0.0:
        raise MetricsError("computed cell areas sum to zero")
    return areas


def get_cell_centres(mesh: pv.DataSet) -> np.ndarray:
    """Return cell-centre coordinates as an `(n_cells, 3)` array."""
    centres = np.asarray(mesh.cell_centers().points, dtype=float)
    if centres.shape != (mesh.n_cells, 3):
        raise MetricsError(f"unexpected cell-centre shape {centres.shape} for {mesh.n_cells} cells")
    return centres


def select_box_region(centres: np.ndarray, xmin: float, xmax: float, ymin: float, ymax: float) -> np.ndarray:
    """Select cells with centres inside an axis-aligned 2D box."""
    if xmax < xmin or ymax < ymin:
        raise MetricsError("invalid box region: expected xmin <= xmax and ymin <= ymax")
    return (centres[:, 0] >= xmin) & (centres[:, 0] <= xmax) & (centres[:, 1] >= ymin) & (centres[:, 1] <= ymax)


def select_circle_region(centres: np.ndarray, xc: float, yc: float, radius: float) -> np.ndarray:
    """Select cells with centres inside a 2D circle."""
    if radius < 0.0:
        raise MetricsError("invalid circle region: radius must be non-negative")
    return (centres[:, 0] - xc) ** 2 + (centres[:, 1] - yc) ** 2 <= radius * radius


def select_region(centres: np.ndarray, region: Region) -> np.ndarray:
    """Dispatch region selection for box or circle definitions."""
    if region.kind == "box":
        return select_box_region(centres, *region.values)
    if region.kind == "circle":
        return select_circle_region(centres, *region.values)
    raise MetricsError(f"unknown region type: {region.kind}")


def area_weighted_mean(values: np.ndarray, areas: np.ndarray) -> float:
    """Return the area-weighted mean of `values`."""
    total_area = float(np.sum(areas))
    if total_area <= 0.0:
        raise MetricsError("cannot compute area-weighted mean over zero area")
    return float(np.sum(values * areas) / total_area)


def pressure_excess_integral(pressure: np.ndarray, areas: np.ndarray, p0: float) -> float:
    """Return area integral of positive pressure excess above `p0`."""
    return float(np.sum(np.maximum(pressure - p0, 0.0) * areas))


def parse_region_from_config(value: Any, name: str) -> Region | None:
    """Parse a region from a config dictionary entry."""
    if value is None:
        return None
    if isinstance(value, Region):
        return value
    if not isinstance(value, dict):
        raise MetricsError(f"{name} must be a Region or dictionary")
    kind = value.get("type")
    if kind == "box":
        keys = ("xmin", "xmax", "ymin", "ymax")
    elif kind == "circle":
        keys = ("xc", "yc", "radius")
    else:
        raise MetricsError(f"{name} region type must be 'box' or 'circle'")
    try:
        values = tuple(float(value[key]) for key in keys)
    except KeyError as exc:
        raise MetricsError(f"{name} region missing key: {exc.args[0]}") from exc
    return Region(kind=kind, values=values)


def monotonic_time_warnings(times: list[float]) -> list[str]:
    """Return warnings for missing, duplicate, or non-monotonic output times."""
    messages = []
    if len(times) < 2:
        messages.append("only one timestep found; pressure impulse set to 0.0")
        return messages
    diffs = np.diff(np.asarray(times, dtype=float))
    if np.any(diffs < 0.0):
        messages.append("non-monotonic times found; histories were sorted by time before integration")
    if np.any(diffs == 0.0):
        messages.append("duplicate output times found; trapezoidal integration may include zero-width intervals")
    return messages


def calculate_histories(config: dict[str, Any]) -> Histories:
    """Read files and calculate per-time histories needed for objective metrics."""
    output_dir = Path(config["output_dir"])
    pressure_field = str(config.get("pressure_field", "pressure"))
    bad_material_field = str(config.get("bad_material_field", "volume_fraction"))
    area_field = config.get("area_field")
    p0 = float(config["p0"])
    target_region = parse_region_from_config(config.get("target_region"), "target")
    interaction_region = parse_region_from_config(config.get("interaction_region"), "interaction")
    if target_region is None:
        raise MetricsError("target region is required")

    files = find_vtu_files(output_dir)
    histories = Histories([], [], [], [], [], [])
    fallback_times_used = 0

    for file_index, path in enumerate(files):
        mesh = pv.read(path)
        pressure = get_cell_array(mesh, pressure_field)
        bad_material = get_cell_array(mesh, bad_material_field)
        areas = get_cell_areas(mesh, area_field)
        centres = get_cell_centres(mesh)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            time = read_time(mesh, fallback=float(file_index))
        fallback_times_used += sum("no TimeValue field" in str(warning.message) for warning in caught)

        target_mask = select_region(centres, target_region)
        target_count = int(np.count_nonzero(target_mask))
        if target_count == 0:
            raise MetricsError(f"empty target region for file {path}")

        if histories.target_n_cells == 0:
            histories.target_n_cells = target_count

        target_pressure = pressure[target_mask]
        target_areas = areas[target_mask]
        histories.times.append(time)
        histories.p95_target.append(float(np.percentile(target_pressure, 95)))
        histories.mean_p_target.append(area_weighted_mean(target_pressure, target_areas))
        histories.mbad_target.append(area_weighted_mean(bad_material[target_mask], target_areas))
        histories.target_excess_integral.append(pressure_excess_integral(target_pressure, target_areas, p0))

        if interaction_region is None:
            histories.interaction_excess_integral.append(np.nan)
            continue

        interaction_mask = select_region(centres, interaction_region)
        interaction_count = int(np.count_nonzero(interaction_mask))
        if interaction_count == 0:
            histories.interaction_excess_integral.append(np.nan)
            continue
        if histories.interaction_n_cells == 0:
            histories.interaction_n_cells = interaction_count
        histories.interaction_excess_integral.append(
            pressure_excess_integral(pressure[interaction_mask], areas[interaction_mask], p0)
        )

    if fallback_times_used:
        warnings.warn(
            f"{fallback_times_used} files had no time metadata; used file-order fallback times",
            RuntimeWarning,
            stacklevel=2,
        )
    return histories


def calculate_metrics(config: dict[str, Any]) -> dict[str, Any]:
    """Calculate scalar optimisation metrics and metadata from a config dictionary."""
    p_incident = float(config["p_incident"])
    p0 = float(config["p0"])
    t_ref = float(config["t_ref"])
    if p_incident <= 0.0:
        raise MetricsError("p_incident must be positive")
    if t_ref <= 0.0:
        raise MetricsError("t_ref must be positive")

    warning_messages: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        histories = calculate_histories(config)
    warning_messages.extend(str(warning.message) for warning in caught)

    order = np.argsort(np.asarray(histories.times, dtype=float))
    times = np.asarray(histories.times, dtype=float)[order]
    p95 = np.asarray(histories.p95_target, dtype=float)[order]
    mean_p = np.asarray(histories.mean_p_target, dtype=float)[order]
    mbad = np.asarray(histories.mbad_target, dtype=float)[order]
    target_excess = np.asarray(histories.target_excess_integral, dtype=float)[order]
    interaction_excess = np.asarray(histories.interaction_excess_integral, dtype=float)[order]

    warning_messages.extend(monotonic_time_warnings(histories.times))
    ap95_index = int(np.argmax(p95))
    mbad_index = int(np.argmax(mbad))

    p_excess_history = np.maximum(mean_p - p0, 0.0)
    if times.size > 1:
        trapezoid = getattr(np, "trapezoid", None)
        if trapezoid is None:
            trapezoid = np.trapz
        ip_raw = float(trapezoid(p_excess_history, times))
    else:
        ip_raw = 0.0

    localisation: float | None = None
    if np.any(np.isfinite(interaction_excess)):
        ratios = np.full_like(target_excess, np.nan, dtype=float)
        valid = np.isfinite(interaction_excess) & (interaction_excess > 0.0)
        ratios[valid] = target_excess[valid] / interaction_excess[valid]
        finite_ratios = ratios[np.isfinite(ratios)]
        if finite_ratios.size:
            localisation = float(np.max(finite_ratios))
        else:
            warning_messages.append("interaction region supplied but no positive interaction excess was found")

    result = {
        "Ap95_target": float(p95[ap95_index] / p_incident),
        "Ip_target": float(ip_raw / (p_incident * t_ref)),
        "Mbad_target": float(mbad[mbad_index]),
        "Lp_localisation": localisation,
        "n_files": int(times.size),
        "time_start": float(times[0]),
        "time_end": float(times[-1]),
        "target_n_cells": int(histories.target_n_cells),
        "interaction_n_cells": int(histories.interaction_n_cells),
        "pressure_field": str(config.get("pressure_field", "pressure")),
        "bad_material_field": str(config.get("bad_material_field", "volume_fraction")),
        "Ap95_target_time": float(times[ap95_index]),
        "Ip_target_raw": ip_raw,
        "Mbad_target_time": float(times[mbad_index]),
        "p_incident": p_incident,
        "p0": p0,
        "t_ref": t_ref,
        "warnings": warning_messages,
    }
    return result


def write_metrics_json(config: dict[str, Any]) -> dict[str, Any]:
    """Calculate metrics, write them to `config["json_out"]`, and return them."""
    result = calculate_metrics(config)
    json_out = Path(config.get("json_out", "metrics.json"))
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def region_from_cli(args: argparse.Namespace, prefix: str) -> dict[str, float | str] | None:
    """Build a region dictionary from argparse box/circle options."""
    box = getattr(args, f"{prefix}_box")
    circle = getattr(args, f"{prefix}_circle")
    if box is not None and circle is not None:
        raise MetricsError(f"provide only one of --{prefix}-box or --{prefix}-circle")
    if box is not None:
        xmin, xmax, ymin, ymax = box
        return {"type": "box", "xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax}
    if circle is not None:
        xc, yc, radius = circle
        return {"type": "circle", "xc": xc, "yc": yc, "radius": radius}
    return None


def build_config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Convert parsed command-line arguments into a config dictionary."""
    config = dict(DEFAULT_CONFIG)
    config.update(
        {
            "output_dir": args.output_dir,
            "json_out": args.json_out,
            "pressure_field": args.pressure_field,
            "bad_material_field": args.bad_material_field,
            "area_field": args.area_field,
            "p_incident": args.p_incident,
            "p0": args.p0,
            "t_ref": args.t_ref,
            "target_region": region_from_cli(args, "target"),
            "interaction_region": region_from_cli(args, "interaction"),
        }
    )
    if config["target_region"] is None:
        raise MetricsError("provide --target-box or --target-circle")
    return config


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--json-out", type=Path, default=Path("metrics.json"))
    parser.add_argument("--pressure-field", default="pressure")
    parser.add_argument("--bad-material-field", default="volume_fraction")
    parser.add_argument("--area-field", help="Optional cell-data area field name, e.g. area or cell_area.")
    parser.add_argument("--p-incident", type=float, required=True)
    parser.add_argument("--p0", type=float, required=True)
    parser.add_argument("--t-ref", type=float, required=True)
    parser.add_argument("--target-box", nargs=4, type=float, metavar=("XMIN", "XMAX", "YMIN", "YMAX"))
    parser.add_argument("--target-circle", nargs=3, type=float, metavar=("XC", "YC", "RADIUS"))
    parser.add_argument("--interaction-box", nargs=4, type=float, metavar=("XMIN", "XMAX", "YMIN", "YMAX"))
    parser.add_argument("--interaction-circle", nargs=3, type=float, metavar=("XC", "YC", "RADIUS"))
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    try:
        args = parse_args()
        config = build_config_from_args(args)
        write_metrics_json(config)
    except MetricsError as exc:
        raise SystemExit(f"error: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
